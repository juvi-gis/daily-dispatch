"""Side effects of approving an article: emailing subscribers and logging."""

import logging
import smtplib

import requests
from django.conf import settings
from django.core.mail import send_mass_mail
from django.db.models import Q

from .models import CustomUser

logger = logging.getLogger(__name__)


def get_subscriber_emails(article):
    """Emails of readers following the article's journalist or publisher."""
    # Build the query in steps: filtering on subscribed_publishers=None would
    # match every reader without any publisher subscription.
    query = Q(subscribed_journalists=article.author)
    if article.publisher_id:
        query |= Q(subscribed_publishers=article.publisher)
    emails = (
        CustomUser.objects.filter(query)
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )
    return list(emails)


def email_subscribers(article):
    """Send the approved article to its subscribers. Returns emails sent."""
    recipients = get_subscriber_emails(article)
    if not recipients:
        return 0

    source = (
        article.publisher.name
        if article.publisher_id
        else "an independent journalist"
    )
    subject = f"New article: {article.title}"
    body = (
        f"{article.title}\n"
        f"By {article.author.username} ({source})\n\n"
        f"{article.content}"
    )
    # One message per reader so addresses are never shown to each other.
    messages = [
        (subject, body, settings.DEFAULT_FROM_EMAIL, [address])
        for address in recipients
    ]
    try:
        return send_mass_mail(messages, fail_silently=False)
    except (smtplib.SMTPException, OSError) as error:
        logger.error(
            "Could not email subscribers for article %s: %s", article.pk, error
        )
        return 0


def post_to_approved_endpoint(article):
    """POST the approved article to our own /api/approved/ endpoint."""
    payload = {
        "article_id": article.pk,
        "title": article.title,
        "author": article.author.username,
        "publisher": article.publisher.name if article.publisher_id else None,
        "created_at": article.created_at.isoformat(),
    }
    try:
        response = requests.post(
            settings.APPROVED_ARTICLE_URL,
            json=payload,
            headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        # Approval must still succeed if the log endpoint is unreachable.
        logger.warning(
            "Could not log approved article %s: %s", article.pk, error
        )
        return False
    return True
