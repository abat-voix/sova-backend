import logging

from django.conf import settings
from django.core.mail import send_mail

from sova.notifications.services.channels.base import NotificationChannelSender

logger = logging.getLogger("django")

EMAIL_SUBJECT_MAX_LENGTH = 120


class EmailChannelSender(NotificationChannelSender):
    """Отправка уведомления на email через настроенный EMAIL_BACKEND."""

    def send(self, target: str, message: str) -> bool:
        """Отправляет message на email target. Тема письма — первая строка message."""
        subject = message.splitlines()[0][:EMAIL_SUBJECT_MAX_LENGTH] if message else ""
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[target],
            )
        except Exception:
            # Любая ошибка бэкенда (SMTP/сеть) не должна прерывать остальные каналы
            logger.exception("Не удалось отправить email-уведомление на %s", target)
            return False
        return True
