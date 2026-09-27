from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from sova.notifications.models import Notification
from sova.notifications.services.message import Message
from sova.notifications.services.notifier import notification_service


@shared_task
def cleanup_notifications() -> int:
    """Удаляет уведомления в системе старше NOTIFICATIONS_RETENTION_DAYS; возвращает число удалённых."""
    threshold = timezone.now() - timedelta(days=settings.NOTIFICATIONS_RETENTION_DAYS)
    deleted, _ = Notification.objects.filter(created_at__lt=threshold).delete()
    return deleted


@shared_task
def send_event_notification(user_ids: list[int], channels: list[str], text: str, kind: str, link: str) -> int:
    """
    Отправляет событийное уведомление пользователям по каналам; возвращает число успешных отправок.

    Пользователи перечитываются по id: между событием и выполнением задачи их могли деактивировать.
    """
    users = list(
        get_user_model()
        .objects.filter(pk__in=user_ids, is_active=True)
        .select_related("notification_profile")
        .order_by("pk"),
    )
    if not users:
        return 0
    results = notification_service.send(
        recipient=users,
        message=Message(text=text, kind=kind, link=link),
        channels=channels,
    )
    return sum(result.success for result in results)
