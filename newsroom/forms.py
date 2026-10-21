from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Article, CustomUser, Newsletter, Publisher, Role


class AdminUserCreationForm(UserCreationForm):
    """Admin form for creating a user with a role."""

    class Meta(UserCreationForm.Meta):
        """Use the custom user model and its extra fields."""

        model = CustomUser
        fields = ("username", "email", "role")


class AdminUserChangeForm(UserChangeForm):
    """Admin form for editing a user, including role and subscriptions."""

    class Meta(UserChangeForm.Meta):
        """Use the custom user model with every field."""

        model = CustomUser
        fields = "__all__"


class RegistrationForm(AdminUserCreationForm):
    """Public sign-up for every role: Reader, Editor or Journalist."""

    email = forms.EmailField(required=True)


class ArticleForm(forms.ModelForm):
    """Create or edit an article; publisher choices depend on the user."""

    class Meta:
        """Fields a journalist or editor can edit."""

        model = Article
        fields = ["title", "content", "publisher"]

    def __init__(self, *args, user, **kwargs):
        """Limit a journalist's publisher choices to their own publishers."""
        super().__init__(*args, **kwargs)
        if user.role == Role.JOURNALIST:
            publishers = user.journalist_publishers.all()
            self.fields["publisher"].queryset = publishers
            if publishers.exists():
                self.fields["publisher"].help_text = (
                    "Pick a publisher to send this article to its editors "
                    "for approval, or leave it independent to publish it "
                    "yourself from My articles."
                )
            else:
                self.fields["publisher"].help_text = (
                    "You are not assigned to a publisher yet, so this will "
                    "be an independent article. An editor can add you to a "
                    "publisher."
                )
        self.fields["publisher"].empty_label = "Independent (no publisher)"


class NewsletterForm(forms.ModelForm):
    """Create or edit a newsletter from approved articles only."""

    articles = forms.ModelMultipleChoiceField(
        queryset=Article.objects.filter(approved=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        """Fields a journalist can edit."""

        model = Newsletter
        fields = ["title", "description", "articles"]


class SubscriptionForm(forms.ModelForm):
    """Let a reader choose publishers and journalists to follow."""

    class Meta:
        """Show both subscription fields as checkboxes."""

        model = CustomUser
        fields = ["subscribed_publishers", "subscribed_journalists"]
        widgets = {
            "subscribed_publishers": forms.CheckboxSelectMultiple,
            "subscribed_journalists": forms.CheckboxSelectMultiple,
        }


class PublisherForm(forms.ModelForm):
    """Create or edit a publisher and choose its editors and journalists."""

    class Meta:
        """Show the staff lists as checkboxes."""

        model = Publisher
        fields = ["name", "description", "editors", "journalists"]
        widgets = {
            "editors": forms.CheckboxSelectMultiple,
            "journalists": forms.CheckboxSelectMultiple,
        }
