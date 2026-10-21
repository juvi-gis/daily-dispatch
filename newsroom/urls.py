from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path("", views.ArticleListView.as_view(), name="article_list"),
    path(
        "articles/new/",
        views.ArticleCreateView.as_view(),
        name="article_create",
    ),
    path(
        "articles/mine/",
        views.MyArticlesView.as_view(),
        name="my_articles",
    ),
    path(
        "articles/pending/",
        views.PendingArticleListView.as_view(),
        name="pending_articles",
    ),
    path(
        "articles/<int:pk>/",
        views.ArticleDetailView.as_view(),
        name="article_detail",
    ),
    path(
        "articles/<int:pk>/edit/",
        views.ArticleUpdateView.as_view(),
        name="article_update",
    ),
    path(
        "articles/<int:pk>/delete/",
        views.ArticleDeleteView.as_view(),
        name="article_delete",
    ),
    path(
        "articles/<int:pk>/publish/",
        views.publish_article,
        name="publish_article",
    ),
    path(
        "articles/<int:pk>/approve/",
        views.approve_article,
        name="approve_article",
    ),
    path(
        "newsletters/",
        views.NewsletterListView.as_view(),
        name="newsletter_list",
    ),
    path(
        "newsletters/new/",
        views.NewsletterCreateView.as_view(),
        name="newsletter_create",
    ),
    path(
        "newsletters/<int:pk>/",
        views.NewsletterDetailView.as_view(),
        name="newsletter_detail",
    ),
    path(
        "newsletters/<int:pk>/edit/",
        views.NewsletterUpdateView.as_view(),
        name="newsletter_update",
    ),
    path(
        "newsletters/<int:pk>/delete/",
        views.NewsletterDeleteView.as_view(),
        name="newsletter_delete",
    ),
    path(
        "subscriptions/",
        views.SubscriptionView.as_view(),
        name="subscriptions",
    ),
    path(
        "publishers/",
        views.PublisherListView.as_view(),
        name="publisher_list",
    ),
    path(
        "publishers/new/",
        views.PublisherCreateView.as_view(),
        name="publisher_create",
    ),
    path(
        "publishers/<int:pk>/edit/",
        views.PublisherUpdateView.as_view(),
        name="publisher_update",
    ),
]
