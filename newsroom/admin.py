from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import (
    ApprovedArticleLog,
    Article,
    CustomUser,
    Newsletter,
    Publisher,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Admin for users, including role and subscriptions."""

    add_form = AdminUserCreationForm
    form = AdminUserChangeForm
    list_display = ("username", "email", "role", "is_staff")
    list_filter = ("role", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Role and subscriptions",
            {
                "fields": (
                    "role",
                    "subscribed_publishers",
                    "subscribed_journalists",
                ),
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {"fields": ("email", "role")}),
    )


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Admin for articles with an approval filter."""

    list_display = ("title", "author", "publisher", "approved", "created_at")
    list_filter = ("approved", "publisher")
    search_fields = ("title", "content")

    def save_model(self, request, obj, form, change):
        """Record who approved a publisher article ticked as approved."""
        if obj.approved and obj.requires_approval and not obj.approved_by_id:
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Publisher)
class PublisherAdmin(admin.ModelAdmin):
    """Admin for publishers with easy staff selection."""

    filter_horizontal = ("editors", "journalists")


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    """Admin for newsletters; only published articles can be chosen."""

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """Offer published articles only."""
        if db_field.name == "articles":
            kwargs["queryset"] = Article.objects.filter(approved=True)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


admin.site.register(ApprovedArticleLog)
