import logging

import requests
from django.conf import settings

from sova.notifications.services.channels.base import NotificationChannelSender
from sova.notifications.services.message import Message

logger = logging.getLogger("django")

# Лимит длины текста sendMessage; длинная сводка уходит несколькими сообщениями
TELEGRAM_MESSAGE_MAX_LENGTH = 4096


class TelegramChannelSender(NotificationChannelSender):
    """Отправка уведомления через Telegram Bot API."""

    def send(self, target: str, message: Message) -> bool:
        """
        Отправляет message в Telegram-чат target через TELEGRAM_BOT_TOKEN; без токена — False без запроса.

        Текст длиннее лимита Telegram уходит частями; успех — только если дошли все части.
        """
        if not settings.TELEGRAM_BOT_TOKEN:
            self._warn_missing_token(setting_name="TELEGRAM_BOT_TOKEN")
            return False
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        request_kwargs = {}
        if settings.TELEGRAM_PROXY:
            request_kwargs["proxies"] = {
                "http": settings.TELEGRAM_PROXY,
                "https": settings.TELEGRAM_PROXY,
            }
        try:
            for text in self._chunks(self._text_with_link(message), limit=TELEGRAM_MESSAGE_MAX_LENGTH):
                response = requests.post(
                    url,
                    data={"chat_id": target, "text": text},
                    timeout=settings.NOTIFICATION_HTTP_TIMEOUT,
                    **request_kwargs,
                )
                response.raise_for_status()
        except requests.RequestException:
            logger.exception("Не удалось отправить Telegram-уведомление на %s", target)
            return False
        return True
