from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.db import DEFAULT_DB_ALIAS
from django.apps import apps as global_apps
from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .models import Article, Newsletter, Role
from .services import email_subscribers, post_to_approved_endpoint

ROLE_PERMISSIONS = {
    Role.READER: ["view_article", "view_newsletter"],
    Role.EDITOR: [
        "view_article",
        "change_article",
        "delete_article",
        "approve_article",
        "view_newsletter",
        "change_newsletter",
        "delete_newsletter",
        "view_publisher",
        "add_publisher",
        "change_publisher",
    ],
    Role.JOURNALIST: [
        "add_article",
        "view_article",
        "change_article",
        "delete_article",
        "add_newsletter",
        "view_newsletter",
        "change_newsletter",
        "delete_newsletter",
    ],
}


def create_role_groups(sender, **kwargs):
    """Create the three role groups and give them their permissions."""
    # Permissions are created by another post_migrate handler whose order is
    # not guaranteed, so make sure they exist before looking them up.
    create_permissions(
        sender,
        verbosity=0,
        using=kwargs.get("using", DEFAULT_DB_ALIAS),
        apps=kwargs.get("apps", global_apps),
    )
    for role, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=Role(role).label)
        group.permissions.set(
            Permission.objects.filter(
                content_type__app_label="newsroom", codename__in=codenames
            )
        )


@receiver(post_save, sender=Article)
def handle_article_approval(sender, instance, **kwargs):
    """Email subscribers and log the article the first time it is approved."""
    if not instance.approved or instance.approval_notified:
        return

    email_subscribers(instance)
    post_to_approved_endpoint(instance)

    # update() skips post_save, so this cannot trigger the receiver again.
    Article.objects.filter(pk=instance.pk).update(approval_notified=True)
    instance.approval_notified = True


@receiver(m2m_changed, sender=Newsletter.articles.through)
def only_published_articles_in_newsletters(
    sender, instance, action, reverse, pk_set, **kwargs
):
    """Refuse to put an unpublished article into a newsletter."""
    if action != "pre_add" or not pk_set:
        return
    if reverse:
        # instance is an Article being added to several newsletters.
        unpublished = not instance.approved
    else:
        unpublished = Article.objects.filter(
            pk__in=pk_set, approved=False
        ).exists()
    if unpublished:
        raise ValidationError(
            "Only published articles can be added to a newsletter."
        )
