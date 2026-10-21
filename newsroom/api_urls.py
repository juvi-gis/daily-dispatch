from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import api_views

router = DefaultRouter()
router.register("articles", api_views.ArticleViewSet, basename="article")
router.register(
    "newsletters", api_views.NewsletterViewSet, basename="newsletter"
)
router.register("publishers", api_views.PublisherViewSet, basename="publisher")

urlpatterns = [
    path("token/", obtain_auth_token, name="api_token"),
    path(
        "users/me/",
        api_views.CurrentUserView.as_view(),
        name="api_current_user",
    ),
    path(
        "approved/",
        api_views.ApprovedArticleLogView.as_view(),
        name="api_approved",
    ),
    path("", include(router.urls)),
]
