import uuid
from dataclasses import dataclass

from django.db import transaction

from sova.notifications.models import NotificationProfile, TelegramLinkToken
from sova.notifications.services.channels.telegram import TelegramChannelSender
from sova.notifications.services.message import Message

_START_HELP_TEXT = (
    "Чтобы подключить уведомления, начните привязку в СОВА: нажмите «Подключить Telegram» "
    "в своём профиле и откройте полученную ссылку."
)
_LINKED_TEXT = "Telegram подключён. Уведомления СОВА будут приходить сюда."
_INVALID_TOKEN_TEXT = "Ссылка недействительна или устарела. Запросите новую в СОВА."
_CHAT_TAKEN_TEXT = "Этот Telegram уже привязан к другому пользователю СОВА."


@dataclass(frozen=True)
class BotUpdateResult:
    """Результат обработки update, включая необязательный ответ пользователю."""

    handled: bool
    reply_text: str | None = None
    chat_id: str | None = None


def handle_update(payload: dict) -> BotUpdateResult:
    """Обрабатывает `/start <одноразовый токен>` из личного Telegram-чата."""
    message = payload.get("message")
    if not isinstance(message, dict):
        return BotUpdateResult(handled=False)

    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return BotUpdateResult(handled=False)

    chat_id = chat.get("id")
    if chat_id is None:
        return BotUpdateResult(handled=False)
    chat_id = str(chat_id)

    text = (message.get("text") or "").strip()
    if not text.startswith("/start"):
        return BotUpdateResult(handled=False)

    token = text.removeprefix("/start").strip()
    if not token:
        return BotUpdateResult(handled=True, reply_text=_START_HELP_TEXT, chat_id=chat_id)

    return BotUpdateResult(handled=True, chat_id=chat_id, reply_text=_link_by_token(token, chat_id))


@transaction.atomic
def _link_by_token(token_value: str, chat_id: str) -> str:
    try:
        token_id = uuid.UUID(token_value)
    except (ValueError, AttributeError, TypeError):
        return _INVALID_TOKEN_TEXT

    token = (
        TelegramLinkToken.objects.select_for_update()
        .select_related("user")
        .filter(pk=token_id)
        .first()
    )
    if token is None or not token.is_valid:
        return _INVALID_TOKEN_TEXT

    taken_by_other = (
        NotificationProfile.objects.filter(telegram_chat_id=chat_id).exclude(user=token.user).exists()
    )
    if taken_by_other:
        return _CHAT_TAKEN_TEXT

    profile, _ = NotificationProfile.objects.get_or_create(user=token.user)
    profile.telegram_chat_id = chat_id
    profile.save(update_fields=["telegram_chat_id"])
    token.mark_used()
    return _LINKED_TEXT


def send_reply(result: BotUpdateResult) -> bool:
    """Отправляет предусмотренный обработкой ответ и сообщает об успехе отправки."""
    if not result.reply_text or not result.chat_id:
        return False
    return TelegramChannelSender().send(result.chat_id, Message(text=result.reply_text))
