import logging
import uuid
from dataclasses import dataclass

from sova.notifications.models import NotificationProfile, TelegramLinkToken
from sova.notifications.services.channels.telegram import TelegramChannelSender
from sova.notifications.services.message import Message

logger = logging.getLogger("sova.telegram_webhook")

_START_HELP_TEXT = (
    "Чтобы подключить уведомления, начните привязку в СОВА: нажмите «Подключить Telegram» "
    "в своём профиле — бот пришлёт одноразовую ссылку."
)
_LINKED_TEXT = "Telegram подключён. Уведомления СОВА будут приходить сюда."
_INVALID_TOKEN_TEXT = "Ссылка недействительна или устарела. Запросите новую в СОВА."
_CHAT_TAKEN_TEXT = "Этот Telegram уже привязан к другому пользователю СОВА."


@dataclass(frozen=True)
class WebhookResult:
    """Итог обработки одного update: что сделали и что ответить пользователю (если нужно)."""

    handled: bool
    reply_text: str | None = None
    chat_id: str | None = None


def handle_update(payload: dict) -> WebhookResult:
    """
    Обрабатывает один Telegram update.

    Привязку принимает только команда `/start <токен>` из личного чата (групповые чаты
    и сообщения без корректного токена не создают и не меняют профиль).
    """
    message = payload.get("message")
    if not isinstance(message, dict):
        logger.info("update_ignored reason=no_message")
        return WebhookResult(handled=False)

    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        logger.info("update_ignored reason=non_private_chat")
        return WebhookResult(handled=False)

    chat_id = chat.get("id")
    if chat_id is None:
        logger.info("update_ignored reason=missing_chat_id")
        return WebhookResult(handled=False)
    chat_id = str(chat_id)

    text = (message.get("text") or "").strip()
    if not text.startswith("/start"):
        logger.info("update_ignored reason=not_start")
        return WebhookResult(handled=False)

    payload_str = text.removeprefix("/start").strip()
    if not payload_str:
        logger.info("start_rejected reason=missing_token")
        return WebhookResult(handled=True, reply_text=_START_HELP_TEXT, chat_id=chat_id)

    logger.info("start_received")
    return WebhookResult(handled=True, chat_id=chat_id, reply_text=_link_by_token(payload_str, chat_id))


def _link_by_token(token_str: str, chat_id: str) -> str:
    try:
        token_id = uuid.UUID(token_str)
    except (ValueError, AttributeError, TypeError):
        logger.info("link_rejected reason=malformed_token")
        return _INVALID_TOKEN_TEXT

    token = TelegramLinkToken.objects.select_related("user").filter(pk=token_id).first()
    if token is None:
        logger.info("link_rejected reason=token_not_found")
        return _INVALID_TOKEN_TEXT
    if not token.is_valid:
        logger.info("link_rejected reason=%s", "token_used" if token.used_at else "token_expired")
        return _INVALID_TOKEN_TEXT

    taken_by_other = (
        NotificationProfile.objects.filter(telegram_chat_id=chat_id).exclude(user=token.user).exists()
    )
    if taken_by_other:
        logger.info("link_rejected reason=chat_already_linked")
        return _CHAT_TAKEN_TEXT

    profile, _ = NotificationProfile.objects.get_or_create(user=token.user)
    profile.telegram_chat_id = chat_id
    profile.save(update_fields=["telegram_chat_id"])

    token.mark_used()
    logger.info("link_created")
    return _LINKED_TEXT


def send_reply(result: WebhookResult) -> None:
    """Отправляет ответное сообщение боту, если обработка его предусматривает."""
    if not result.reply_text or not result.chat_id:
        return
    logger.info("reply_started")
    sent = TelegramChannelSender().send(result.chat_id, Message(text=result.reply_text))
    logger.info("reply_finished sent=%s", sent)
