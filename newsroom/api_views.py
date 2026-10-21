import hmac
import logging

from django.conf import settings
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ApprovedArticleLog, Article, Newsletter, Publisher, Role
from .permissions import (
    ArticleRolePermission,
    AuthorOrEditorCanModify,
    ModelPermissionsWithView,
)
from .serializers import (
    ArticleSerializer,
    NewsletterSerializer,
    PublisherSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


class ArticleViewSet(viewsets.ModelViewSet):
    """Article endpoints with role-based access."""

    serializer_class = ArticleSerializer
    permission_classes = [IsAuthenticated, ArticleRolePermission]

    def get_queryset(self):
        """Choose which articles this user may see for this action."""
        user = self.request.user
        articles = Article.objects.select_related("author", "publisher")

        if self.action in ("list", "subscribed"):
            return articles.filter(approved=True)
        if user.role == Role.EDITOR:
            return articles
        if user.role == Role.JOURNALIST:
            return articles.filter(Q(approved=True) | Q(author=user))
        return articles.filter(approved=True)

    def perform_create(self, serializer):
        """Set the logged-in journalist as author."""
        serializer.save(author=self.request.user)

    @action(detail=False, methods=["get"])
    def subscribed(self, request):
        """Approved articles from the reader's journalists and publishers."""
        user = request.user
        articles = self.get_queryset().filter(
            Q(author__in=user.subscribed_journalists.all())
            | Q(publisher__in=user.subscribed_publishers.all())
        )
        serializer = self.get_serializer(articles, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Editor-only: approve an article and trigger notifications."""
        article = self.get_object()
        if not article.requires_approval:
            return Response(
                {"detail": "Independent articles need no approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if article.approved:
            return Response(
                {"detail": "Article is already approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        article.approved = True
        article.approved_by = request.user
        article.save()  # post_save signal sends the emails and the log POST
        return Response(self.get_serializer(article).data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Journalist-only: publish your own independent article."""
        article = self.get_object()
        if article.requires_approval:
            return Response(
                {"detail": "Articles under a publisher need editor approval."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if article.approved:
            return Response(
                {"detail": "Article is already published."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        article.publish()  # post_save signal emails subscribers and logs it
        return Response(self.get_serializer(article).data)


class NewsletterViewSet(viewsets.ModelViewSet):
    """Newsletter endpoints using group permissions."""

    queryset = Newsletter.objects.select_related("author").prefetch_related(
        "articles"
    )
    serializer_class = NewsletterSerializer
    # Group permissions decide who can add/change/delete; ownership narrows it.
    permission_classes = [ModelPermissionsWithView, AuthorOrEditorCanModify]

    def perform_create(self, serializer):
        """Set the logged-in journalist as author."""
        serializer.save(author=self.request.user)


class PublisherViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list of publishers."""

    queryset = Publisher.objects.all()
    serializer_class = PublisherSerializer


class CurrentUserView(APIView):
    """Return the user who owns the token."""

    def get(self, request):
        """Serialize the current user."""
        return Response(UserSerializer(request.user).data)


class ApprovedArticleLogView(APIView):
    """Receives the POST sent by the approval signal and stores a log row."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """Check the shared token, then store the log entry."""
        sent_token = request.headers.get("X-Internal-Token", "")
        if not hmac.compare_digest(sent_token, settings.INTERNAL_API_TOKEN):
            return Response(status=status.HTTP_403_FORBIDDEN)

        article_id = request.data.get("article_id")
        title = request.data.get("title")
        if not article_id or not title:
            return Response(
                {"detail": "article_id and title are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_entry = ApprovedArticleLog.objects.create(
            article=Article.objects.filter(pk=article_id).first(),
            title=title,
            payload=request.data,
        )
        logger.info("Approved article logged: %s", log_entry)
        return Response(
            {"logged": log_entry.pk}, status=status.HTTP_201_CREATED
        )
