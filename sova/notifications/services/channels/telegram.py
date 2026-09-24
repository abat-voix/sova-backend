import logging

import requests
from django.conf import settings

from sova.notifications.services.channels.base import NotificationChannelSender
from sova.notifications.services.message import Message

logger = logging.getLogger("django")


class TelegramChannelSender(NotificationChannelSender):
    """Отправка уведомления через Telegram Bot API."""

    def send(self, target: str, message: Message) -> bool:
        """Отправляет message в Telegram-чат target через TELEGRAM_BOT_TOKEN."""
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            response = requests.post(
                url,
                data={"chat_id": target, "text": message.text},
                timeout=settings.NOTIFICATION_HTTP_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Не удалось отправить Telegram-уведомление на %s", target)
            return False
        return True
