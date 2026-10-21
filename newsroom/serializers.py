from rest_framework import serializers

from .models import Article, CustomUser, Newsletter, Publisher


class UserSerializer(serializers.ModelSerializer):
    """Read-only view of a user and their subscriptions."""

    class Meta:
        """Fields exposed by the API."""

        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "role",
            "subscribed_publishers",
            "subscribed_journalists",
        ]
        read_only_fields = fields


class PublisherSerializer(serializers.ModelSerializer):
    """Read-only view of a publisher and its staff."""

    class Meta:
        """Fields exposed by the API."""

        model = Publisher
        fields = ["id", "name", "description", "editors", "journalists"]
        read_only_fields = fields


class ArticleSerializer(serializers.ModelSerializer):
    """Article data; approval is not writable here."""

    author = serializers.StringRelatedField(read_only=True)
    publisher = serializers.PrimaryKeyRelatedField(
        queryset=Publisher.objects.all(), allow_null=True, required=False
    )
    status = serializers.ReadOnlyField()

    class Meta:
        """Fields exposed by the API; approved is read-only."""

        model = Article
        fields = [
            "id",
            "title",
            "content",
            "author",
            "publisher",
            "created_at",
            "approved",
            "status",
        ]
        # Approval only happens through the editor-only approve action.
        read_only_fields = ["id", "author", "created_at", "approved"]

    def validate_publisher(self, publisher):
        """Check the author writes for the chosen publisher."""
        author = (
            self.instance.author
            if self.instance
            else self.context["request"].user
        )
        if (
            publisher
            and not publisher.journalists.filter(pk=author.pk).exists()
        ):
            raise serializers.ValidationError(
                "The author does not write for this publisher."
            )
        return publisher


class NewsletterSerializer(serializers.ModelSerializer):
    """Newsletter data with article ids."""

    author = serializers.StringRelatedField(read_only=True)
    articles = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Article.objects.all(), required=False
    )

    class Meta:
        """Fields exposed by the API."""

        model = Newsletter
        fields = [
            "id",
            "title",
            "description",
            "created_at",
            "author",
            "articles",
        ]
        read_only_fields = ["id", "created_at", "author"]

    def validate_articles(self, articles):
        """Only approved articles can go in a newsletter."""
        unapproved = [
            article.pk for article in articles if not article.approved
        ]
        if unapproved:
            raise serializers.ValidationError(
                f"Only approved articles can be added. Not approved: "
                f"{unapproved}"
            )
        return articles
