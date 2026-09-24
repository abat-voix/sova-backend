import logging

import requests
from django.conf import settings

from sova.notifications.services.channels.base import NotificationChannelSender
from sova.notifications.services.message import Message

logger = logging.getLogger("django")


class MaxChannelSender(NotificationChannelSender):
    """Отправка уведомления через MAX Bot API (platform-api.max.ru)."""

    def send(self, target: str, message: Message) -> bool:
        """Отправляет message в MAX-чат target через MAX_BOT_TOKEN."""
        url = f"{settings.MAX_API_URL}/messages"
        try:
            response = requests.post(
                url,
                params={"chat_id": target},
                json={"text": message.text},
                headers={"Authorization": f"Bearer {settings.MAX_BOT_TOKEN}"},
                timeout=settings.NOTIFICATION_HTTP_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Не удалось отправить MAX-уведомление на %s", target)
            return False
        return True
