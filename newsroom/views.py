from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UserPassesTestMixin,
)
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import (
    ArticleForm,
    NewsletterForm,
    PublisherForm,
    RegistrationForm,
    SubscriptionForm,
)
from .models import Article, Newsletter, Publisher, Role


def editable_queryset(model, user):
    """Editors can change anything; journalists only what they wrote."""
    if user.role == Role.EDITOR:
        return model.objects.all()
    return model.objects.filter(author=user)


class RegisterView(CreateView):
    """Public sign-up for every role; the new user is logged in at once."""

    form_class = RegistrationForm
    template_name = "registration/register.html"
    success_url = reverse_lazy("article_list")

    def form_valid(self, form):
        """Save the user, log them in and send them to the site."""
        user = form.save()
        self.object = user
        login(self.request, user)
        messages.success(
            self.request, f"Welcome, {user.username}! Your account is ready."
        )
        return redirect(self.get_success_url())


# ---------- Articles ----------


class ArticleListView(LoginRequiredMixin, ListView):
    """Paginated list of approved articles."""

    queryset = Article.objects.filter(approved=True).select_related(
        "author", "publisher"
    )
    context_object_name = "articles"
    paginate_by = 10


class ArticleDetailView(LoginRequiredMixin, DetailView):
    """One article; drafts are only visible to their author and editors."""

    template_name = "newsroom/article_detail.html"

    def get_queryset(self):
        """Editors see everything; others see approved or their own."""
        user = self.request.user
        articles = Article.objects.select_related("author", "publisher")
        if user.role == Role.EDITOR:
            return articles
        # Unapproved drafts are only visible to their own author.
        return articles.filter(Q(approved=True) | Q(author=user))

    def get_context_data(self, **kwargs):
        """Add flags for the Edit/Delete and Publish buttons."""
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["can_modify"] = user.has_perm("newsroom.change_article") and (
            user.role == Role.EDITOR or self.object.author == user
        )
        # Only the author of an unpublished independent article can publish.
        context["can_publish"] = (
            self.object.author == user
            and not self.object.requires_approval
            and not self.object.approved
            and user.has_perm("newsroom.change_article")
        )
        return context


class ArticleCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    CreateView,
):
    """Create an article: a draft if independent, pending if publisher."""

    permission_required = "newsroom.add_article"
    form_class = ArticleForm
    template_name = "newsroom/article_form.html"
    success_url = reverse_lazy("my_articles")

    def get_success_message(self, cleaned_data):
        """Explain what happens next to this article."""
        if self.object.requires_approval:
            return (
                f"Submitted to {self.object.publisher}. An editor needs to "
                "approve it before it is published."
            )
        return "Saved as a draft. Click Publish when it is ready for readers."

    def get_form_kwargs(self):
        """Pass the user and a pre-filled author to the form."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        # Setting the author up front lets the model validate the publisher.
        kwargs["instance"] = Article(author=self.request.user)
        return kwargs


class ArticleUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    UpdateView,
):
    """Edit an article (own for journalists, any for editors)."""

    permission_required = "newsroom.change_article"
    form_class = ArticleForm
    template_name = "newsroom/article_form.html"
    success_message = "Article updated."

    def get_queryset(self):
        """Limit which articles this user may edit."""
        return editable_queryset(Article, self.request.user)

    def get_form_kwargs(self):
        """Pass the user to the form."""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        """Return to the edited article."""
        return reverse_lazy("article_detail", kwargs={"pk": self.object.pk})


class ArticleDeleteView(
    LoginRequiredMixin, PermissionRequiredMixin, DeleteView
):
    """Confirm and delete an article."""

    permission_required = "newsroom.delete_article"
    template_name = "newsroom/confirm_delete.html"

    def get_queryset(self):
        """Limit which articles this user may delete."""
        return editable_queryset(Article, self.request.user)

    def get_success_url(self):
        """Journalists return to their own list; editors to the main list."""
        if self.request.user.role == Role.JOURNALIST:
            return reverse("my_articles")
        return reverse("article_list")


# ---------- Editor review ----------


class PendingArticleListView(
    LoginRequiredMixin, PermissionRequiredMixin, ListView
):
    """Editor review queue of unapproved articles."""

    permission_required = "newsroom.approve_article"
    template_name = "newsroom/pending_articles.html"
    context_object_name = "articles"
    # Independent drafts never need an editor, so they stay out of the queue.
    queryset = Article.objects.filter(
        approved=False, publisher__isnull=False
    ).select_related("author", "publisher")


@login_required
@permission_required("newsroom.approve_article", raise_exception=True)
@require_POST
def approve_article(request, pk):
    """Approve an article; the post_save signal then emails subscribers."""
    article = get_object_or_404(Article, pk=pk)
    if not article.requires_approval:
        messages.error(
            request, "Independent articles are published by their author."
        )
    elif article.approved:
        messages.info(request, "That article was already approved.")
    else:
        article.approved = True
        article.approved_by = request.user
        article.save()  # the post_save signal emails subscribers
        messages.success(
            request, f"'{article.title}' approved and sent to subscribers."
        )
    return redirect("pending_articles")


# ---------- Journalist: my articles and publishing ----------


class MyArticlesView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """A journalist's own articles grouped by status."""

    permission_required = "newsroom.add_article"
    template_name = "newsroom/my_articles.html"
    context_object_name = "articles"

    def get_queryset(self):
        """Only the logged-in journalist's articles."""
        return Article.objects.filter(author=self.request.user).select_related(
            "publisher"
        )

    def get_context_data(self, **kwargs):
        """Split the articles into drafts, pending and published."""
        context = super().get_context_data(**kwargs)
        articles = list(context["articles"])
        context["drafts"] = [a for a in articles if a.status == "draft"]
        context["pending"] = [a for a in articles if a.status == "pending"]
        context["published"] = [a for a in articles if a.status == "published"]
        return context


@login_required
@permission_required("newsroom.change_article", raise_exception=True)
@require_POST
def publish_article(request, pk):
    """Publish one of your own independent drafts."""
    article = get_object_or_404(Article, pk=pk, author=request.user)
    if article.requires_approval:
        messages.error(
            request,
            "Articles under a publisher are approved by an editor, not "
            "published by the author.",
        )
    elif article.approved:
        messages.info(request, "That article is already published.")
    else:
        article.publish()  # the post_save signal emails subscribers
        messages.success(
            request,
            f"'{article.title}' is published and subscribers were emailed.",
        )
    return redirect("my_articles")


# ---------- Publishers (editors manage them) ----------


class PublisherListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Publishers with their editors and journalists."""

    permission_required = "newsroom.view_publisher"
    template_name = "newsroom/publisher_list.html"
    context_object_name = "publishers"
    queryset = Publisher.objects.prefetch_related("editors", "journalists")


class PublisherCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    CreateView,
):
    """Create a publisher and choose its editors and journalists."""

    permission_required = "newsroom.add_publisher"
    form_class = PublisherForm
    template_name = "newsroom/publisher_form.html"
    success_url = reverse_lazy("publisher_list")
    success_message = "Publisher created."

    def form_valid(self, form):
        """Save, then make sure the creating editor is one of its editors."""
        response = super().form_valid(form)
        self.object.editors.add(self.request.user)
        return response


class PublisherUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    UpdateView,
):
    """Change a publisher's details, editors and journalists."""

    permission_required = "newsroom.change_publisher"
    model = Publisher
    form_class = PublisherForm
    template_name = "newsroom/publisher_form.html"
    success_url = reverse_lazy("publisher_list")
    success_message = "Publisher updated."


# ---------- Newsletters ----------


class NewsletterListView(LoginRequiredMixin, ListView):
    """Paginated list of newsletters."""

    model = Newsletter
    context_object_name = "newsletters"
    paginate_by = 10


class NewsletterDetailView(LoginRequiredMixin, DetailView):
    """One newsletter with its articles."""

    model = Newsletter


class NewsletterCreateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    CreateView,
):
    """Journalists create a newsletter."""

    permission_required = "newsroom.add_newsletter"
    form_class = NewsletterForm
    template_name = "newsroom/newsletter_form.html"
    success_url = reverse_lazy("newsletter_list")
    success_message = "Newsletter created."

    def form_valid(self, form):
        """Set the logged-in journalist as author."""
        form.instance.author = self.request.user
        return super().form_valid(form)


class NewsletterUpdateView(
    LoginRequiredMixin,
    PermissionRequiredMixin,
    SuccessMessageMixin,
    UpdateView,
):
    """Edit a newsletter (own for journalists, any for editors)."""

    permission_required = "newsroom.change_newsletter"
    form_class = NewsletterForm
    template_name = "newsroom/newsletter_form.html"
    success_url = reverse_lazy("newsletter_list")
    success_message = "Newsletter updated."

    def get_queryset(self):
        """Limit which newsletters this user may edit."""
        return editable_queryset(Newsletter, self.request.user)


class NewsletterDeleteView(
    LoginRequiredMixin, PermissionRequiredMixin, DeleteView
):
    """Confirm and delete a newsletter."""

    permission_required = "newsroom.delete_newsletter"
    template_name = "newsroom/confirm_delete.html"
    success_url = reverse_lazy("newsletter_list")

    def get_queryset(self):
        """Limit which newsletters this user may delete."""
        return editable_queryset(Newsletter, self.request.user)


# ---------- Subscriptions ----------


class SubscriptionView(
    LoginRequiredMixin, UserPassesTestMixin, SuccessMessageMixin, UpdateView
):
    """Readers manage who they follow."""

    form_class = SubscriptionForm
    template_name = "newsroom/subscriptions.html"
    success_url = reverse_lazy("subscriptions")
    success_message = "Subscriptions saved."

    def test_func(self):
        """Only readers may open this page."""
        return self.request.user.role == Role.READER

    def get_object(self, queryset=None):
        """Edit the logged-in user's own subscriptions."""
        return self.request.user
