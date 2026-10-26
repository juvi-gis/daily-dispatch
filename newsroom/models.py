"""Database models for the Daily Dispatch newsroom."""

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group
from django.core.exceptions import ValidationError
from django.db import models


class Role(models.TextChoices):
    """The three roles a user can have; each maps to a group."""

    READER = "reader", "Reader"
    EDITOR = "editor", "Editor"
    JOURNALIST = "journalist", "Journalist"


class CustomUser(AbstractUser):
    """User with a role; the role decides the group and the extra fields."""

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.READER
    )
    # Reader-only fields.
    subscribed_publishers = models.ManyToManyField(
        "Publisher", related_name="subscribers", blank=True
    )
    subscribed_journalists = models.ManyToManyField(
        "self",
        symmetrical=False,
        related_name="subscribers",
        blank=True,
        limit_choices_to={"role": Role.JOURNALIST},
    )

    def clean(self):
        """Reject an email address that another account already uses."""
        super().clean()
        if (
            self.email
            and CustomUser.objects.filter(email__iexact=self.email)
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError(
                {"email": "A user with this email address already exists."}
            )

    def save(self, *args, **kwargs):
        """Save the user, then match their group and fields to their role."""
        super().save(*args, **kwargs)
        self.sync_role_group()
        if self.role != Role.READER:
            # M2M fields cannot hold None, so "no value" means no rows.
            self.subscribed_publishers.clear()
            self.subscribed_journalists.clear()

    def sync_role_group(self):
        """Put the user in their role group and remove other role groups."""
        role_group, _ = Group.objects.get_or_create(name=Role(self.role).label)
        other_role_groups = Group.objects.filter(name__in=Role.labels).exclude(
            pk=role_group.pk
        )
        self.groups.remove(*other_role_groups)
        self.groups.add(role_group)

    @property
    def independent_articles(self):
        """Articles a journalist published without a publisher."""
        if self.role != Role.JOURNALIST:
            return self.articles.none()
        return self.articles.filter(publisher__isnull=True)

    @property
    def independent_newsletters(self):
        """Newsletters a journalist published on their own."""
        if self.role != Role.JOURNALIST:
            return self.newsletters.none()
        return self.newsletters.all()

    def __str__(self):
        """Show the username."""
        return self.username


class Publisher(models.Model):
    """A publication with its own editors and journalists."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    editors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="editor_publishers",
        blank=True,
        limit_choices_to={"role": Role.EDITOR},
    )
    journalists = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="journalist_publishers",
        blank=True,
        limit_choices_to={"role": Role.JOURNALIST},
    )

    class Meta:
        """List publishers alphabetically."""

        ordering = ["name"]

    def __str__(self):
        """Show the publisher name."""
        return self.name


class Article(models.Model):
    """A news article: independent (self-published) or under a publisher."""

    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="articles",
        limit_choices_to={"role": Role.JOURNALIST},
    )
    # Null publisher means the article is independent.
    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.CASCADE,
        related_name="articles",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="approved_articles",
        null=True,
        blank=True,
        editable=False,
    )
    # Guards the approval signal so subscribers are only emailed once.
    approval_notified = models.BooleanField(default=False, editable=False)

    class Meta:
        """Newest first, plus the custom approve permission."""

        ordering = ["-created_at"]
        permissions = [("approve_article", "Can approve articles")]

    def clean(self):
        """Check the author is a journalist at the chosen publisher."""
        if not self.author_id:
            return
        if self.author.role != Role.JOURNALIST:
            raise ValidationError(
                {"author": "The author must be a journalist."}
            )
        if (
            self.publisher_id
            and not self.publisher.journalists.filter(
                pk=self.author_id
            ).exists()
        ):
            raise ValidationError(
                {"publisher": "This author does not write for that publisher."}
            )

    @property
    def requires_approval(self):
        """Publisher articles need an editor; independent ones do not."""
        return self.publisher_id is not None

    @property
    def status(self):
        """One of: published, pending (waiting for an editor) or draft."""
        if self.approved:
            return "published"
        if self.requires_approval:
            return "pending"
        return "draft"

    def publish(self):
        """Publish an independent article; post_save then notifies readers."""
        if self.requires_approval:
            raise ValueError("Publisher articles are approved by an editor.")
        self.approved = True
        self.save()

    def save(self, *args, **kwargs):
        """Drop any old approval when the article changes publisher."""
        if self.pk:
            previous_publisher_id = (
                Article.objects.filter(pk=self.pk)
                .values_list("publisher_id", flat=True)
                .first()
            )
            if previous_publisher_id != self.publisher_id:
                # Moving in or out of a publisher must not carry an old
                # approval or publication along with it.
                self.approved = False
                self.approved_by = None
                self.approval_notified = False
        super().save(*args, **kwargs)

    def __str__(self):
        """Show the article title."""
        return self.title


class Newsletter(models.Model):
    """A curated collection of approved articles by one journalist."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="newsletters",
        limit_choices_to={"role": Role.JOURNALIST},
    )
    articles = models.ManyToManyField(
        Article, related_name="newsletters", blank=True
    )

    class Meta:
        """List newsletters newest first."""

        ordering = ["-created_at"]

    def __str__(self):
        """Show the newsletter title."""
        return self.title


class ApprovedArticleLog(models.Model):
    """One row per approval received at /api/approved/."""

    article = models.ForeignKey(
        Article, on_delete=models.SET_NULL, null=True, blank=True
    )
    title = models.CharField(max_length=200)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """List log entries newest first."""

        ordering = ["-received_at"]

    def __str__(self):
        """Show which article was approved."""
        return f"Approved: {self.title}"
