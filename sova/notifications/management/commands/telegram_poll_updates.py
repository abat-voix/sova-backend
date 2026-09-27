import json
import logging
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sova.notifications.services import telegram_bot

logger = logging.getLogger("django")

_POLL_TIMEOUT_SECONDS = 25
_RETRY_DELAY_SECONDS = 5


class Command(BaseCommand):
    """Получает Telegram updates через long polling и обрабатывает команды привязки."""

    help = "Запускает long polling Telegram Bot API для обработки /start <токен>."

    def handle(self, *args, **options) -> None:
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN не задан")

        self.stdout.write("Telegram long polling запущен.")
        offset: int | None = None
        while True:
            try:
                updates = self._get_updates(offset)
            except requests.RequestException:
                logger.exception(
                    "Не удалось получить Telegram updates; повтор через %s секунд",
                    _RETRY_DELAY_SECONDS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
                continue

            for update in updates:
                update_id = update.get("update_id")
                if not isinstance(update_id, int):
                    logger.warning("Telegram update без целочисленного update_id пропущен")
                    continue
                try:
                    result = telegram_bot.handle_update(update)
                    telegram_bot.send_reply(result)
                    logger.info(
                        "Telegram update обработан: update_id=%s handled=%s",
                        update_id,
                        result.handled,
                    )
                except Exception:
                    logger.exception("Ошибка обработки Telegram update_id=%s", update_id)
                finally:
                    offset = update_id + 1

    def _get_updates(self, offset: int | None) -> list[dict]:
        request_kwargs = {}
        if settings.TELEGRAM_PROXY:
            request_kwargs["proxies"] = {
                "http": settings.TELEGRAM_PROXY,
                "https": settings.TELEGRAM_PROXY,
            }
        params = {
            "timeout": _POLL_TIMEOUT_SECONDS,
            "allowed_updates": json.dumps(["message"]),
        }
        if offset is not None:
            params["offset"] = offset

        response = requests.get(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates",
            params=params,
            timeout=_POLL_TIMEOUT_SECONDS + settings.NOTIFICATION_HTTP_TIMEOUT,
            **request_kwargs,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok") or not isinstance(payload.get("result"), list):
            raise requests.RequestException("Telegram вернул некорректный ответ getUpdates")
        return payload["result"]
