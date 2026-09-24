from celery import shared_task
from django.utils import timezone

from sova.notifications.services.deadline_dispatch import deadline_dispatch_service
from sova.processes.services.deadlines import deadline_service


@shared_task
def notify_deadlines() -> dict:
    """Уведомляет о просроченных и приближающихся сроках действий, этапов и процессов."""
    now = timezone.now()
    items = deadline_service.collect(now=now)
    return deadline_dispatch_service.dispatch(items=items, now=now)
