from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.utils import timezone

from sova.notifications.models import NotificationProfile, TelegramLinkToken


@dataclass(frozen=True)
class TelegramLinkStatus:
    """Статус привязки Telegram для отображения на фронтенде."""

    is_connected: bool
    deep_link: str | None
    expires_at: datetime | None


def build_deep_link(token: TelegramLinkToken) -> str | None:
    """Deep-ссылка https://t.me/<бот>?start=<токен>; None — если бот не настроен."""
    if not settings.TELEGRAM_BOT_USERNAME:
        return None
    return f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={token.id}"


def issue_link_token(user: AbstractBaseUser) -> TelegramLinkToken:
    """Создаёт новый одноразовый токен привязки для пользователя."""
    ttl = timedelta(minutes=settings.TELEGRAM_LINK_TOKEN_TTL_MINUTES)
    return TelegramLinkToken.objects.create(user=user, expires_at=timezone.now() + ttl)


def get_link_status(user: AbstractBaseUser) -> TelegramLinkStatus:
    """
    Текущий статус привязки: подключён ли Telegram, и ссылка для подключения, если нет.

    Если у пользователя уже есть действующий неиспользованный токен — возвращает
    ссылку по нему, не создавая новый (повторные открытия страницы не плодят токены).
    """
    profile = getattr(user, "notification_profile", None)
    chat_id = profile.telegram_chat_id if profile else ""
    if chat_id:
        return TelegramLinkStatus(is_connected=True, deep_link=None, expires_at=None)

    token = (
        TelegramLinkToken.objects.filter(user=user, used_at__isnull=True, expires_at__gt=timezone.now())
        .order_by("-created_at")
        .first()
    )
    if token is None:
        token = issue_link_token(user)
    return TelegramLinkStatus(is_connected=False, deep_link=build_deep_link(token), expires_at=token.expires_at)


def disconnect(user: AbstractBaseUser) -> None:
    """Отключает Telegram: очищает telegram_chat_id в профиле пользователя."""
    NotificationProfile.objects.filter(user=user).update(telegram_chat_id="")
