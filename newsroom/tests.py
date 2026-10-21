from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import ApprovedArticleLog, Article, Newsletter, Publisher, Role

User = get_user_model()
PASSWORD = "StrongPass!234"


def make_user(username, role, email=None):
    """Create a user with the given role and a default email."""
    return User.objects.create_user(
        username=username,
        password=PASSWORD,
        role=role,
        email=email if email is not None else f"{username}@example.com",
    )


class NewsTestBase:
    """Shared users, publisher and articles for the API and web tests."""

    def setUp(self):
        # Stop the approval signal from making real HTTP calls in every test.
        """Create users, a publisher and sample articles."""
        post_patcher = patch("newsroom.services.requests.post")
        self.mock_post = post_patcher.start()
        self.addCleanup(post_patcher.stop)

        self.reader = make_user("reader", Role.READER)
        self.other_reader = make_user("other_reader", Role.READER)
        self.journalist = make_user("journalist", Role.JOURNALIST)
        self.other_journalist = make_user("other_journalist", Role.JOURNALIST)
        self.editor = make_user("editor", Role.EDITOR)

        self.publisher = Publisher.objects.create(name="The Daily Test")
        self.publisher.journalists.add(self.journalist)
        self.publisher.editors.add(self.editor)
        self.other_publisher = Publisher.objects.create(name="Other Press")

        self.publisher_article = Article.objects.create(
            title="Publisher story",
            content="Body",
            author=self.journalist,
            publisher=self.publisher,
            approved=True,
        )
        self.independent_article = Article.objects.create(
            title="Independent story",
            content="Body",
            author=self.other_journalist,
            approved=True,
        )
        self.draft_article = Article.objects.create(
            title="Draft story",
            content="Body",
            author=self.journalist,
            publisher=self.publisher,
        )

        # The reader follows the publisher only.
        self.reader.subscribed_publishers.add(self.publisher)

        # Creating the approved fixtures above fired the approval signal.
        self.mock_post.reset_mock()
        mail.outbox.clear()


class RoleAndGroupTests(NewsTestBase, TestCase):
    """Roles map to groups, permissions and cleared subscriptions."""

    def test_user_is_placed_in_group_for_role(self):
        self.assertEqual(
            list(self.journalist.groups.values_list("name", flat=True)),
            ["Journalist"],
        )

    def test_changing_role_swaps_group(self):
        self.reader.role = Role.EDITOR
        self.reader.save()
        self.assertEqual(
            list(self.reader.groups.values_list("name", flat=True)), ["Editor"]
        )

    def test_group_permissions(self):
        self.assertTrue(self.reader.has_perm("newsroom.view_article"))
        self.assertFalse(self.reader.has_perm("newsroom.add_article"))
        self.assertTrue(self.editor.has_perm("newsroom.approve_article"))
        self.assertTrue(self.editor.has_perm("newsroom.add_publisher"))
        self.assertTrue(self.editor.has_perm("newsroom.change_publisher"))
        self.assertFalse(self.journalist.has_perm("newsroom.add_publisher"))
        self.assertFalse(self.reader.has_perm("newsroom.view_publisher"))
        self.assertFalse(self.editor.has_perm("newsroom.add_article"))
        self.assertTrue(self.journalist.has_perm("newsroom.add_article"))
        self.assertFalse(self.journalist.has_perm("newsroom.approve_article"))

    def test_journalist_has_no_reader_subscriptions(self):
        self.journalist.subscribed_publishers.add(self.publisher)
        self.journalist.save()
        self.assertEqual(self.journalist.subscribed_publishers.count(), 0)
        self.assertEqual(self.journalist.subscribed_journalists.count(), 0)

    def test_independent_articles_only_for_journalists(self):
        self.assertEqual(self.other_journalist.independent_articles.count(), 1)
        self.assertEqual(self.journalist.independent_articles.count(), 0)
        self.assertEqual(self.reader.independent_articles.count(), 0)


class TokenAuthTests(NewsTestBase, APITestCase):
    """Token login and unauthenticated access."""

    def test_login_returns_token(self):
        response = self.client.post(
            reverse("api_token"), {"username": "reader", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)

    def test_wrong_password_is_rejected(self):
        response = self.client.post(
            reverse("api_token"), {"username": "reader", "password": "nope"}
        )
        self.assertEqual(response.status_code, 400)

    def test_requests_without_token_are_rejected(self):
        self.assertEqual(self.client.get("/api/articles/").status_code, 401)

    def test_token_gives_access(self):
        token = Token.objects.create(user=self.reader)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(self.client.get("/api/articles/").status_code, 200)

    def test_current_user_endpoint(self):
        self.client.force_authenticate(self.reader)
        response = self.client.get("/api/users/me/")
        self.assertEqual(response.data["username"], "reader")
        self.assertEqual(response.data["role"], "reader")


class ArticleReadApiTests(NewsTestBase, APITestCase):
    """Which articles each role can read through the API."""

    def titles(self, response):
        """Return the set of article titles in a response."""
        return {article["title"] for article in response.data}

    def test_list_returns_only_approved_articles_for_every_role(self):
        for user in (self.reader, self.journalist, self.editor):
            self.client.force_authenticate(user)
            response = self.client.get("/api/articles/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                self.titles(response), {"Publisher story", "Independent story"}
            )

    def test_subscribed_returns_only_subscribed_sources(self):
        self.client.force_authenticate(self.reader)
        response = self.client.get("/api/articles/subscribed/")
        self.assertEqual(self.titles(response), {"Publisher story"})

    def test_subscribed_includes_followed_journalist(self):
        self.reader.subscribed_journalists.add(self.other_journalist)
        self.client.force_authenticate(self.reader)
        response = self.client.get("/api/articles/subscribed/")
        self.assertEqual(
            self.titles(response), {"Publisher story", "Independent story"}
        )

    def test_reader_without_subscriptions_gets_empty_list(self):
        self.client.force_authenticate(self.other_reader)
        response = self.client.get("/api/articles/subscribed/")
        self.assertEqual(response.data, [])

    def test_subscribed_is_reader_only(self):
        self.client.force_authenticate(self.journalist)
        self.assertEqual(
            self.client.get("/api/articles/subscribed/").status_code, 403
        )

    def test_retrieve_approved_article(self):
        self.client.force_authenticate(self.reader)
        response = self.client.get(
            f"/api/articles/{self.publisher_article.pk}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Publisher story")

    def test_reader_cannot_retrieve_draft(self):
        self.client.force_authenticate(self.reader)
        response = self.client.get(f"/api/articles/{self.draft_article.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_author_and_editor_can_retrieve_draft(self):
        for user in (self.journalist, self.editor):
            self.client.force_authenticate(user)
            response = self.client.get(
                f"/api/articles/{self.draft_article.pk}/"
            )
            self.assertEqual(response.status_code, 200)

    def test_other_journalist_cannot_retrieve_draft(self):
        self.client.force_authenticate(self.other_journalist)
        response = self.client.get(f"/api/articles/{self.draft_article.pk}/")
        self.assertEqual(response.status_code, 404)


class ArticleWriteApiTests(NewsTestBase, APITestCase):
    """Creating, updating and deleting articles through the API."""

    new_article = {"title": "Fresh", "content": "New content"}

    def test_independent_article_starts_as_draft(self):
        self.client.force_authenticate(self.other_journalist)
        response = self.client.post("/api/articles/", self.new_article)
        self.assertEqual(response.status_code, 201)
        article = Article.objects.get(pk=response.data["id"])
        self.assertEqual(article.author, self.other_journalist)
        self.assertFalse(article.approved)
        self.assertEqual(response.data["status"], "draft")
        self.assertIsNone(article.publisher)

    def test_journalist_can_create_publisher_article(self):
        self.client.force_authenticate(self.journalist)
        data = {**self.new_article, "publisher": self.publisher.pk}
        response = self.client.post("/api/articles/", data)
        self.assertEqual(response.status_code, 201)

    def test_journalist_cannot_publish_for_foreign_publisher(self):
        self.client.force_authenticate(self.journalist)
        data = {**self.new_article, "publisher": self.other_publisher.pk}
        response = self.client.post("/api/articles/", data)
        self.assertEqual(response.status_code, 400)
        self.assertIn("publisher", response.data)

    def test_create_cannot_self_approve(self):
        self.client.force_authenticate(self.journalist)
        data = {**self.new_article, "approved": True}
        response = self.client.post("/api/articles/", data)
        self.assertFalse(response.data["approved"])
        self.mock_post.assert_not_called()

    def test_missing_title_is_rejected(self):
        self.client.force_authenticate(self.journalist)
        response = self.client.post("/api/articles/", {"content": "No title"})
        self.assertEqual(response.status_code, 400)

    def test_reader_and_editor_cannot_create(self):
        for user in (self.reader, self.editor):
            self.client.force_authenticate(user)
            response = self.client.post("/api/articles/", self.new_article)
            self.assertEqual(response.status_code, 403)

    def test_journalist_can_update_own_article(self):
        self.client.force_authenticate(self.journalist)
        response = self.client.put(
            f"/api/articles/{self.draft_article.pk}/",
            {"title": "Changed", "content": "Changed body"},
        )
        self.assertEqual(response.status_code, 200)
        self.draft_article.refresh_from_db()
        self.assertEqual(self.draft_article.title, "Changed")

    def test_journalist_cannot_update_someone_elses_article(self):
        self.client.force_authenticate(self.other_journalist)
        response = self.client.put(
            f"/api/articles/{self.publisher_article.pk}/",
            {"title": "Hijack", "content": "x"},
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_can_update_any_article(self):
        self.client.force_authenticate(self.editor)
        response = self.client.patch(
            f"/api/articles/{self.publisher_article.pk}/", {"title": "Edited"}
        )
        self.assertEqual(response.status_code, 200)

    def test_editor_update_cannot_flip_approved_flag(self):
        self.client.force_authenticate(self.editor)
        self.client.patch(
            f"/api/articles/{self.draft_article.pk}/", {"approved": True}
        )
        self.draft_article.refresh_from_db()
        self.assertFalse(self.draft_article.approved)

    def test_reader_cannot_update(self):
        self.client.force_authenticate(self.reader)
        response = self.client.put(
            f"/api/articles/{self.publisher_article.pk}/",
            {"title": "x", "content": "x"},
        )
        self.assertEqual(response.status_code, 403)

    def test_editor_can_delete(self):
        self.client.force_authenticate(self.editor)
        response = self.client.delete(
            f"/api/articles/{self.publisher_article.pk}/"
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            Article.objects.filter(pk=self.publisher_article.pk).exists()
        )

    def test_journalist_can_delete_own_but_not_others(self):
        self.client.force_authenticate(self.journalist)
        own = self.client.delete(f"/api/articles/{self.draft_article.pk}/")
        others = self.client.delete(
            f"/api/articles/{self.independent_article.pk}/"
        )
        self.assertEqual(own.status_code, 204)
        self.assertEqual(others.status_code, 403)

    def test_reader_cannot_delete(self):
        self.client.force_authenticate(self.reader)
        response = self.client.delete(
            f"/api/articles/{self.publisher_article.pk}/"
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            Article.objects.filter(pk=self.publisher_article.pk).exists()
        )


class ApprovalApiTests(NewsTestBase, APITestCase):
    """Only editors can approve, and approving notifies subscribers."""

    def approve_url(self, article):
        """Build the approve URL for an article."""
        return f"/api/articles/{article.pk}/approve/"

    def test_editor_can_approve(self):
        self.client.force_authenticate(self.editor)
        response = self.client.post(self.approve_url(self.draft_article))
        self.assertEqual(response.status_code, 200)
        self.draft_article.refresh_from_db()
        self.assertTrue(self.draft_article.approved)
        self.assertEqual(self.draft_article.approved_by, self.editor)

    def test_journalist_and_reader_cannot_approve(self):
        for user in (self.journalist, self.reader):
            self.client.force_authenticate(user)
            response = self.client.post(self.approve_url(self.draft_article))
            self.assertEqual(response.status_code, 403)
        self.draft_article.refresh_from_db()
        self.assertFalse(self.draft_article.approved)

    def test_approving_twice_fails(self):
        self.client.force_authenticate(self.editor)
        response = self.client.post(self.approve_url(self.publisher_article))
        self.assertEqual(response.status_code, 400)

    def test_approval_triggers_email_and_log_post(self):
        self.client.force_authenticate(self.editor)
        self.client.post(self.approve_url(self.draft_article))
        self.assertEqual(len(mail.outbox), 1)
        self.mock_post.assert_called_once()


class NewsletterApiTests(NewsTestBase, APITestCase):
    """Newsletter permissions and validation through the API."""

    def setUp(self):
        """Add one newsletter on top of the shared fixtures."""
        super().setUp()
        self.newsletter = Newsletter.objects.create(
            title="Weekly", description="Top stories", author=self.journalist
        )
        self.newsletter.articles.add(self.publisher_article)

    def test_reader_can_view_newsletters(self):
        self.client.force_authenticate(self.reader)
        response = self.client.get("/api/newsletters/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data[0]["articles"], [self.publisher_article.pk]
        )

    def test_reader_cannot_create_or_delete(self):
        self.client.force_authenticate(self.reader)
        create = self.client.post("/api/newsletters/", {"title": "x"})
        delete = self.client.delete(f"/api/newsletters/{self.newsletter.pk}/")
        self.assertEqual(create.status_code, 403)
        self.assertEqual(delete.status_code, 403)

    def test_journalist_can_create_newsletter(self):
        self.client.force_authenticate(self.journalist)
        response = self.client.post(
            "/api/newsletters/",
            {
                "title": "New",
                "description": "d",
                "articles": [self.independent_article.pk],
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Newsletter.objects.get(pk=response.data["id"]).author,
            self.journalist,
        )

    def test_newsletter_rejects_unapproved_article(self):
        self.client.force_authenticate(self.journalist)
        response = self.client.post(
            "/api/newsletters/",
            {"title": "New", "articles": [self.draft_article.pk]},
        )
        self.assertEqual(response.status_code, 400)

    def test_editor_can_update_and_delete_but_not_create(self):
        self.client.force_authenticate(self.editor)
        update = self.client.patch(
            f"/api/newsletters/{self.newsletter.pk}/", {"title": "Edited"}
        )
        create = self.client.post("/api/newsletters/", {"title": "x"})
        delete = self.client.delete(f"/api/newsletters/{self.newsletter.pk}/")
        self.assertEqual(update.status_code, 200)
        self.assertEqual(create.status_code, 403)
        self.assertEqual(delete.status_code, 204)

    def test_journalist_cannot_edit_another_journalists_newsletter(self):
        self.client.force_authenticate(self.other_journalist)
        response = self.client.patch(
            f"/api/newsletters/{self.newsletter.pk}/", {"title": "Hijack"}
        )
        self.assertEqual(response.status_code, 403)

    def test_publishers_are_readable(self):
        self.client.force_authenticate(self.reader)
        response = self.client.get("/api/publishers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)


class ApprovalSignalTests(NewsTestBase, TestCase):
    """Emails and the log POST sent by the approval signal."""

    def approve(self, article):
        """Approve an article by saving it, as the signal expects."""
        article.approved = True
        article.save()

    def test_publisher_article_emails_publisher_subscribers(self):
        self.approve(self.draft_article)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reader@example.com"])
        self.assertIn("Draft story", mail.outbox[0].subject)

    def test_independent_article_only_emails_journalist_subscribers(self):
        self.other_reader.subscribed_journalists.add(self.other_journalist)
        solo = Article.objects.create(
            title="Solo", content="x", author=self.other_journalist
        )
        self.assertEqual(len(mail.outbox), 0)  # a draft sends nothing
        solo.publish()
        recipients = [message.to[0] for message in mail.outbox]
        # The publisher-only subscriber must not get an independent article.
        self.assertEqual(recipients, ["other_reader@example.com"])

    def test_reader_following_both_sources_gets_one_email(self):
        self.reader.subscribed_journalists.add(self.journalist)
        self.approve(self.draft_article)
        self.assertEqual(len(mail.outbox), 1)

    def test_unapproved_save_sends_nothing(self):
        self.draft_article.title = "Retitled"
        self.draft_article.save()
        self.assertEqual(len(mail.outbox), 0)
        self.mock_post.assert_not_called()

    def test_posts_payload_to_approved_endpoint(self):
        self.approve(self.draft_article)
        self.mock_post.assert_called_once()
        _, kwargs = self.mock_post.call_args
        self.assertEqual(kwargs["json"]["article_id"], self.draft_article.pk)
        self.assertEqual(kwargs["json"]["publisher"], "The Daily Test")
        self.assertIn("X-Internal-Token", kwargs["headers"])

    def test_notification_only_happens_once(self):
        self.approve(self.draft_article)
        self.draft_article.save()
        self.assertEqual(len(mail.outbox), 1)
        self.mock_post.assert_called_once()

    def test_unreachable_endpoint_does_not_break_approval(self):
        self.mock_post.side_effect = requests.ConnectionError("down")
        self.approve(self.draft_article)
        self.draft_article.refresh_from_db()
        self.assertTrue(self.draft_article.approved)
        self.assertEqual(len(mail.outbox), 1)

    @patch(
        "newsroom.services.send_mass_mail", side_effect=OSError("smtp down")
    )
    def test_email_failure_does_not_break_approval(self, mock_mail):
        self.approve(self.draft_article)
        self.draft_article.refresh_from_db()
        self.assertTrue(self.draft_article.approved)
        self.mock_post.assert_called_once()


class ApprovedEndpointTests(NewsTestBase, APITestCase):
    """The /api/approved/ log endpoint and its shared token."""

    payload = {"article_id": 1, "title": "Logged story"}

    def test_valid_post_is_logged(self):
        response = self.client.post(
            "/api/approved/",
            self.payload,
            format="json",
            HTTP_X_INTERNAL_TOKEN="dev-internal-token",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            ApprovedArticleLog.objects.get().title, "Logged story"
        )

    def test_missing_or_wrong_token_is_forbidden(self):
        missing = self.client.post(
            "/api/approved/", self.payload, format="json"
        )
        wrong = self.client.post(
            "/api/approved/",
            self.payload,
            format="json",
            HTTP_X_INTERNAL_TOKEN="wrong",
        )
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(ApprovedArticleLog.objects.count(), 0)

    def test_incomplete_payload_is_rejected(self):
        response = self.client.post(
            "/api/approved/",
            {"article_id": 1},
            format="json",
            HTTP_X_INTERNAL_TOKEN="dev-internal-token",
        )
        self.assertEqual(response.status_code, 400)


class WebViewTests(NewsTestBase, TestCase):
    """Access control and behaviour of the HTML views."""

    def test_login_required(self):
        response = self.client.get(reverse("article_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_reader_sees_only_approved_articles(self):
        self.client.force_login(self.reader)
        response = self.client.get(reverse("article_list"))
        self.assertContains(response, "Publisher story")
        self.assertNotContains(response, "Draft story")

    def test_editor_review_queue_access(self):
        pending_url = reverse("pending_articles")
        self.client.force_login(self.editor)
        self.assertContains(self.client.get(pending_url), "Draft story")
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(pending_url).status_code, 403)

    def test_editor_approves_through_view(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("approve_article", args=[self.draft_article.pk])
        )
        self.assertRedirects(response, reverse("pending_articles"))
        self.draft_article.refresh_from_db()
        self.assertTrue(self.draft_article.approved)
        self.assertEqual(len(mail.outbox), 1)

    def test_reader_and_journalist_cannot_approve(self):
        url = reverse("approve_article", args=[self.draft_article.pk])
        for user in (self.reader, self.journalist):
            self.client.force_login(user)
            self.assertEqual(self.client.post(url).status_code, 403)

    def test_approve_requires_post(self):
        self.client.force_login(self.editor)
        response = self.client.get(
            reverse("approve_article", args=[self.draft_article.pk])
        )
        self.assertEqual(response.status_code, 405)

    def test_journalist_creates_article(self):
        self.client.force_login(self.journalist)
        response = self.client.post(
            reverse("article_create"),
            {
                "title": "Web story",
                "content": "Text",
                "publisher": self.publisher.pk,
            },
        )
        self.assertRedirects(response, reverse("my_articles"))
        article = Article.objects.get(title="Web story")
        self.assertEqual(article.author, self.journalist)
        self.assertFalse(article.approved)
        self.assertEqual(article.status, "pending")

    def test_reader_cannot_open_create_page(self):
        self.client.force_login(self.reader)
        self.assertEqual(
            self.client.get(reverse("article_create")).status_code, 403
        )

    def test_journalist_cannot_edit_others_article(self):
        self.client.force_login(self.other_journalist)
        response = self.client.get(
            reverse("article_update", args=[self.publisher_article.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_reader_can_save_subscriptions(self):
        self.client.force_login(self.other_reader)
        self.client.post(
            reverse("subscriptions"),
            {
                "subscribed_publishers": [self.publisher.pk],
                "subscribed_journalists": [self.journalist.pk],
            },
        )
        self.assertEqual(self.other_reader.subscribed_publishers.count(), 1)
        self.assertEqual(self.other_reader.subscribed_journalists.count(), 1)

    def test_journalist_cannot_open_subscriptions(self):
        self.client.force_login(self.journalist)
        self.assertEqual(
            self.client.get(reverse("subscriptions")).status_code, 403
        )

    def test_registration_form_offers_every_role(self):
        response = self.client.get(reverse("register"))
        for role in ("reader", "editor", "journalist"):
            self.assertContains(response, f'value="{role}"')

    def test_registered_editor_gets_editor_access(self):
        self.client.post(
            reverse("register"),
            {
                "username": "new_editor",
                "email": "ne@example.com",
                "role": "editor",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        editor = User.objects.get(username="new_editor")
        self.assertEqual(editor.role, Role.EDITOR)
        self.assertEqual(
            list(editor.groups.values_list("name", flat=True)), ["Editor"]
        )
        self.client.login(username="new_editor", password=PASSWORD)
        self.assertEqual(
            self.client.get(reverse("pending_articles")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("article_create")).status_code, 403
        )

    def test_registered_editor_can_approve_through_api(self):
        self.client.post(
            reverse("register"),
            {
                "username": "api_editor",
                "email": "ae@example.com",
                "role": "editor",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        editor = User.objects.get(username="api_editor")
        self.client.force_login(editor)
        response = self.client.post(
            reverse("approve_article", args=[self.draft_article.pk])
        )
        self.assertRedirects(response, reverse("pending_articles"))
        self.draft_article.refresh_from_db()
        self.assertTrue(self.draft_article.approved)

    def test_registration_creates_reader(self):
        self.client.post(
            reverse("register"),
            {
                "username": "newbie",
                "email": "n@example.com",
                "role": "reader",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertEqual(User.objects.get(username="newbie").role, Role.READER)

    def test_registration_logs_the_new_user_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "autologin",
                "email": "auto@example.com",
                "role": "reader",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("article_list"))
        user = User.objects.get(username="autologin")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_duplicate_email_is_rejected(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "copycat",
                "email": "READER@example.com",
                "role": "reader",
                "password1": PASSWORD,
                "password2": PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertFalse(User.objects.filter(username="copycat").exists())

    def test_unique_email_check_ignores_the_user_themselves(self):
        self.reader.first_name = "Renamed"
        self.reader.full_clean()  # must not complain about its own email


class ArticleApprovalRuleTests(NewsTestBase, APITestCase):
    """Independent drafts are published by the author; others need review."""

    new_article = {"title": "Rule test", "content": "Body"}

    def create_independent_draft(self):
        self.client.force_authenticate(self.other_journalist)
        response = self.client.post("/api/articles/", self.new_article)
        return response.data["id"]

    def create_publisher_article(self):
        self.client.force_authenticate(self.journalist)
        data = {**self.new_article, "publisher": self.publisher.pk}
        return self.client.post("/api/articles/", data).data["id"]

    def test_requires_approval_and_status(self):
        independent = Article(
            title="a", content="b", author=self.other_journalist
        )
        under_publisher = Article(
            title="a",
            content="b",
            author=self.journalist,
            publisher=self.publisher,
        )
        self.assertFalse(independent.requires_approval)
        self.assertEqual(independent.status, "draft")
        self.assertTrue(under_publisher.requires_approval)
        self.assertEqual(under_publisher.status, "pending")
        independent.approved = True
        self.assertEqual(independent.status, "published")

    def test_draft_is_hidden_from_readers_until_published(self):
        article_id = self.create_independent_draft()
        self.client.force_authenticate(self.reader)
        titles = {a["title"] for a in self.client.get("/api/articles/").data}
        self.assertNotIn("Rule test", titles)
        self.client.force_authenticate(self.other_journalist)
        response = self.client.post(f"/api/articles/{article_id}/publish/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "published")
        self.client.force_authenticate(self.reader)
        titles = {a["title"] for a in self.client.get("/api/articles/").data}
        self.assertIn("Rule test", titles)

    def test_publishing_notifies_subscribers_and_logs(self):
        self.other_reader.subscribed_journalists.add(self.other_journalist)
        article_id = self.create_independent_draft()
        self.assertEqual(len(mail.outbox), 0)
        self.client.post(f"/api/articles/{article_id}/publish/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["other_reader@example.com"])
        self.mock_post.assert_called_once()

    def test_publish_twice_fails(self):
        article_id = self.create_independent_draft()
        self.client.post(f"/api/articles/{article_id}/publish/")
        response = self.client.post(f"/api/articles/{article_id}/publish/")
        self.assertEqual(response.status_code, 400)

    def test_publisher_article_cannot_be_self_published(self):
        article_id = self.create_publisher_article()
        response = self.client.post(f"/api/articles/{article_id}/publish/")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Article.objects.get(pk=article_id).approved)
        self.assertEqual(len(mail.outbox), 0)

    def test_only_the_author_can_publish(self):
        article_id = self.create_independent_draft()
        for user in (self.journalist, self.editor, self.reader):
            self.client.force_authenticate(user)
            response = self.client.post(f"/api/articles/{article_id}/publish/")
            self.assertIn(response.status_code, (403, 404))
        self.assertFalse(Article.objects.get(pk=article_id).approved)

    def test_cannot_force_approved_flag_on_create(self):
        self.client.force_authenticate(self.journalist)
        data = {
            **self.new_article,
            "publisher": self.publisher.pk,
            "approved": True,
        }
        response = self.client.post("/api/articles/", data)
        self.assertFalse(response.data["approved"])
        self.assertEqual(response.data["status"], "pending")

    def test_editor_approves_publisher_article(self):
        article_id = self.create_publisher_article()
        self.client.force_authenticate(self.editor)
        response = self.client.post(f"/api/articles/{article_id}/approve/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "published")

    def test_editor_cannot_approve_independent_article(self):
        article_id = self.create_independent_draft()
        self.client.force_authenticate(self.editor)
        response = self.client.post(f"/api/articles/{article_id}/approve/")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Article.objects.get(pk=article_id).approved)

    def test_moving_a_published_article_under_a_publisher_resets_it(self):
        article_id = self.create_independent_draft()
        self.client.post(f"/api/articles/{article_id}/publish/")
        self.publisher.journalists.add(self.other_journalist)
        response = self.client.patch(
            f"/api/articles/{article_id}/", {"publisher": self.publisher.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["approved"])
        self.assertEqual(response.data["status"], "pending")

    def test_independent_articles_stay_out_of_the_review_queue(self):
        self.create_independent_draft()
        self.client.force_login(self.editor)
        queue = self.client.get(reverse("pending_articles"))
        self.assertNotContains(queue, "Rule test")


class WriteAndPublishWebTests(NewsTestBase, TestCase):
    """Write article form, My articles page and the Publish button."""

    def test_write_form_shows_publisher_choice_to_house_journalist(self):
        self.client.force_login(self.journalist)
        response = self.client.get(reverse("article_create"))
        self.assertContains(response, 'name="publisher"')
        self.assertContains(response, "The Daily Test")

    def test_write_form_explains_when_no_publisher_is_assigned(self):
        self.client.force_login(self.other_journalist)
        response = self.client.get(reverse("article_create"))
        self.assertContains(response, 'name="publisher"')
        self.assertContains(response, "not assigned to a publisher")

    def test_independent_article_is_saved_as_draft(self):
        self.client.force_login(self.other_journalist)
        response = self.client.post(
            reverse("article_create"),
            {"title": "My draft", "content": "Text"},
            follow=True,
        )
        article = Article.objects.get(title="My draft")
        self.assertFalse(article.approved)
        self.assertContains(response, "Saved as a draft")

    def test_my_articles_groups_by_status(self):
        draft = Article.objects.create(
            title="Draft one", content="x", author=self.other_journalist
        )
        self.client.force_login(self.other_journalist)
        response = self.client.get(reverse("my_articles"))
        self.assertContains(response, "Draft one")
        self.assertContains(
            response, reverse("publish_article", args=[draft.pk])
        )
        self.assertContains(
            response, reverse("article_update", args=[draft.pk])
        )
        self.assertContains(
            response, reverse("article_delete", args=[draft.pk])
        )
        self.assertNotContains(response, "Publisher story")

    def test_my_articles_lists_pending_publisher_articles(self):
        self.client.force_login(self.journalist)
        response = self.client.get(reverse("my_articles"))
        self.assertContains(response, "Draft story")
        pending_url = reverse("publish_article", args=[self.draft_article.pk])
        self.assertNotContains(response, pending_url)

    def test_readers_and_editors_cannot_open_my_articles(self):
        for user in (self.reader, self.editor):
            self.client.force_login(user)
            self.assertEqual(
                self.client.get(reverse("my_articles")).status_code, 403
            )

    def test_publish_button_only_on_independent_drafts(self):
        independent = Article.objects.create(
            title="Solo draft", content="x", author=self.other_journalist
        )
        self.client.force_login(self.other_journalist)
        page = self.client.get(
            reverse("article_detail", args=[independent.pk])
        )
        self.assertContains(
            page, reverse("publish_article", args=[independent.pk])
        )
        self.client.force_login(self.journalist)
        page = self.client.get(
            reverse("article_detail", args=[self.draft_article.pk])
        )
        self.assertNotContains(
            page, reverse("publish_article", args=[self.draft_article.pk])
        )

    def test_publish_button_hidden_once_published(self):
        self.client.force_login(self.other_journalist)
        page = self.client.get(
            reverse("article_detail", args=[self.independent_article.pk])
        )
        self.assertNotContains(
            page,
            reverse("publish_article", args=[self.independent_article.pk]),
        )

    def test_publish_view_publishes_and_emails(self):
        self.other_reader.subscribed_journalists.add(self.other_journalist)
        draft = Article.objects.create(
            title="Go live", content="x", author=self.other_journalist
        )
        self.client.force_login(self.other_journalist)
        response = self.client.post(
            reverse("publish_article", args=[draft.pk])
        )
        self.assertRedirects(response, reverse("my_articles"))
        draft.refresh_from_db()
        self.assertTrue(draft.approved)
        self.assertEqual(len(mail.outbox), 1)

    def test_publish_view_refuses_publisher_articles(self):
        self.client.force_login(self.journalist)
        self.client.post(
            reverse("publish_article", args=[self.draft_article.pk])
        )
        self.draft_article.refresh_from_db()
        self.assertFalse(self.draft_article.approved)
        self.assertEqual(len(mail.outbox), 0)

    def test_publish_view_is_post_only_and_author_only(self):
        draft = Article.objects.create(
            title="Mine", content="x", author=self.other_journalist
        )
        url = reverse("publish_article", args=[draft.pk])
        self.client.force_login(self.other_journalist)
        self.assertEqual(self.client.get(url).status_code, 405)
        for user in (self.journalist, self.editor):
            self.client.force_login(user)
            self.assertIn(self.client.post(url).status_code, (403, 404))
        self.client.force_login(self.reader)
        self.assertEqual(self.client.post(url).status_code, 403)
        draft.refresh_from_db()
        self.assertFalse(draft.approved)

    def test_approve_view_refuses_independent_articles(self):
        draft = Article.objects.create(
            title="Solo", content="x", author=self.other_journalist
        )
        self.client.force_login(self.editor)
        self.client.post(reverse("approve_article", args=[draft.pk]))
        draft.refresh_from_db()
        self.assertFalse(draft.approved)


class PublisherManagementTests(NewsTestBase, TestCase):
    """Editors create publishers and assign editors and journalists."""

    def test_editor_sees_publisher_list(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("publisher_list"))
        self.assertContains(response, "The Daily Test")
        self.assertContains(response, "journalist")

    def test_reader_and_journalist_cannot_manage_publishers(self):
        for user in (self.reader, self.journalist):
            self.client.force_login(user)
            for name in ("publisher_list", "publisher_create"):
                self.assertEqual(
                    self.client.get(reverse(name)).status_code, 403
                )

    def test_editor_creates_publisher_and_assigns_people(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("publisher_create"),
            {
                "name": "Fresh Press",
                "description": "New house",
                "journalists": [self.other_journalist.pk],
            },
        )
        self.assertRedirects(response, reverse("publisher_list"))
        publisher = Publisher.objects.get(name="Fresh Press")
        self.assertIn(self.editor, publisher.editors.all())
        self.assertIn(self.other_journalist, publisher.journalists.all())

    def test_editor_can_assign_more_staff_later(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse("publisher_update", args=[self.other_publisher.pk]),
            {
                "name": "Other Press",
                "description": "",
                "editors": [self.editor.pk],
                "journalists": [self.other_journalist.pk],
            },
        )
        self.assertEqual(self.other_publisher.journalists.count(), 1)

    def test_only_journalists_and_editors_appear_in_the_choices(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("publisher_create"))
        form = response.context["form"]
        journalist_roles = {
            u.role for u in form.fields["journalists"].queryset
        }
        editor_roles = {u.role for u in form.fields["editors"].queryset}
        self.assertEqual(journalist_roles, {Role.JOURNALIST})
        self.assertEqual(editor_roles, {Role.EDITOR})

    def test_assigned_journalist_can_then_write_for_the_publisher(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse("publisher_update", args=[self.other_publisher.pk]),
            {
                "name": "Other Press",
                "description": "",
                "journalists": [self.other_journalist.pk],
            },
        )
        self.client.force_login(self.other_journalist)
        response = self.client.post(
            reverse("article_create"),
            {
                "title": "For Other Press",
                "content": "Body",
                "publisher": self.other_publisher.pk,
            },
        )
        self.assertRedirects(response, reverse("my_articles"))
        article = Article.objects.get(title="For Other Press")
        self.assertEqual(article.status, "pending")


class NewsletterPublishedOnlyTests(NewsTestBase, TestCase):
    """Only published articles can be put into a newsletter."""

    def test_form_lists_only_published_articles(self):
        self.client.force_login(self.journalist)
        response = self.client.get(reverse("newsletter_create"))
        self.assertContains(response, "Publisher story")
        self.assertNotContains(response, "Draft story")

    def test_posting_an_unpublished_article_is_rejected(self):
        self.client.force_login(self.journalist)
        response = self.client.post(
            reverse("newsletter_create"),
            {
                "title": "Sneaky",
                "description": "",
                "articles": [self.draft_article.pk],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Newsletter.objects.filter(title="Sneaky").exists())

    def test_published_article_can_be_added(self):
        self.client.force_login(self.journalist)
        self.client.post(
            reverse("newsletter_create"),
            {
                "title": "Fine",
                "description": "",
                "articles": [self.publisher_article.pk],
            },
        )
        newsletter = Newsletter.objects.get(title="Fine")
        self.assertEqual(newsletter.articles.count(), 1)

    def test_model_level_guard_blocks_unpublished_articles(self):
        newsletter = Newsletter.objects.create(
            title="Guarded", author=self.journalist
        )
        # Each failed add rolls back its own savepoint.
        with transaction.atomic(), self.assertRaises(ValidationError):
            newsletter.articles.add(self.draft_article)
        with transaction.atomic(), self.assertRaises(ValidationError):
            self.draft_article.newsletters.add(newsletter)
        self.assertEqual(newsletter.articles.count(), 0)
