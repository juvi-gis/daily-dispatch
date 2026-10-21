from django.apps import AppConfig
from django.db.models.signals import post_migrate


class NewsroomConfig(AppConfig):
    """App configuration that registers signals and role groups."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "newsroom"

    def ready(self):
        # Importing registers the post_save receiver for article approval.
        """Connect the approval signal and group creation."""
        from . import signals

        post_migrate.connect(signals.create_role_groups, sender=self)
