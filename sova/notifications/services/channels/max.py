import logging

import requests
from django.conf import settings

from sova.notifications.services.channels.base import NotificationChannelSender
from sova.notifications.services.message import Message

logger = logging.getLogger("django")

# Лимит длины текста сообщения MAX; длинная сводка уходит несколькими сообщениями
MAX_MESSAGE_MAX_LENGTH = 4000


class MaxChannelSender(NotificationChannelSender):
    """Отправка уведомления через MAX Bot API (platform-api.max.ru)."""

    def send(self, target: str, message: Message) -> bool:
        """
        Отправляет message в MAX-чат target через MAX_BOT_TOKEN; без токена — False без запроса.

        Текст длиннее лимита MAX уходит частями; успех — только если дошли все части.
        """
        if not settings.MAX_BOT_TOKEN:
            self._warn_missing_token(setting_name="MAX_BOT_TOKEN")
            return False
        url = f"{settings.MAX_API_URL}/messages"
        try:
            for text in self._chunks(self._text_with_link(message), limit=MAX_MESSAGE_MAX_LENGTH):
                response = requests.post(
                    url,
                    params={"chat_id": target},
                    json={"text": text},
                    headers={"Authorization": f"Bearer {settings.MAX_BOT_TOKEN}"},
                    timeout=settings.NOTIFICATION_HTTP_TIMEOUT,
                )
                response.raise_for_status()
        except requests.RequestException:
            logger.exception("Не удалось отправить MAX-уведомление на %s", target)
            return False
        return True
