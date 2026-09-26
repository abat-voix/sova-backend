from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from sova.messaging.services.message_attachment import message_attachment_service


@shared_task
def cleanup_staged_message_attachments() -> int:
    """Удаляет неотправленные файлы, срок хранения которых истёк."""
    before = timezone.now() - timedelta(hours=settings.MESSAGE_ATTACHMENT_STAGING_TTL_HOURS)
    return message_attachment_service.cleanup_staged(before)
