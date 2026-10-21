from rest_framework.permissions import BasePermission, DjangoModelPermissions

from .models import Role

EVERY_ROLE = {Role.READER, Role.EDITOR, Role.JOURNALIST}

ARTICLE_ACTION_ROLES = {
    "list": EVERY_ROLE,
    "retrieve": EVERY_ROLE,
    "subscribed": {Role.READER},
    "create": {Role.JOURNALIST},
    "update": {Role.JOURNALIST, Role.EDITOR},
    "partial_update": {Role.JOURNALIST, Role.EDITOR},
    "destroy": {Role.JOURNALIST, Role.EDITOR},
    "approve": {Role.EDITOR},
    "publish": {Role.JOURNALIST},
}


class ArticleRolePermission(BasePermission):
    """Role rules for the article endpoints (used after IsAuthenticated)."""

    def has_permission(self, request, view):
        """Allow the action only for roles listed for it."""
        allowed_roles = ARTICLE_ACTION_ROLES.get(view.action)
        return bool(allowed_roles) and request.user.role in allowed_roles

    def has_object_permission(self, request, view, obj):
        """Journalists may only change their own articles."""
        return _journalist_owns_or_is_editor(request.user, view, obj)


class ModelPermissionsWithView(DjangoModelPermissions):
    """DjangoModelPermissions that also requires view permission on reads."""

    perms_map = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
    }


class AuthorOrEditorCanModify(BasePermission):
    """Journalists may only change their own objects; editors any."""

    def has_object_permission(self, request, view, obj):
        """Reads are open; writes need ownership or the editor role."""
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return _journalist_owns_or_is_editor(request.user, view, obj)


def _journalist_owns_or_is_editor(user, view, obj):
    """Journalists must own the object to change it; editors always may."""
    if user.role == Role.JOURNALIST and view.action in (
        "update",
        "partial_update",
        "destroy",
        "publish",
    ):
        return obj.author_id == user.id
    return True
