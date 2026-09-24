from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser


@dataclass
class Recipient:
    """Адреса получателя уведомления по каналам email/Telegram/MAX и id пользователя для системного канала."""

    email: str | None = None
    telegram_chat_id: str | None = None
    max_chat_id: str | None = None
    user_id: int | None = None

    @classmethod
    def for_user(cls, user: AbstractBaseUser) -> "Recipient":
        """
        Собирает адреса получателя из NotificationProfile (если есть) и user.email.

        email берётся из профиля, если он там указан; иначе — из user.email.
        Telegram/MAX адресов вне профиля не существует, поэтому без профиля
        они всегда None. user_id — адрес системного канала; у Recipient, собранного
        вручную, его нет.
        """
        profile = getattr(user, "notification_profile", None)
        profile_email = (profile.email or None) if profile else None
        return cls(
            email=profile_email or (user.email or None),
            telegram_chat_id=(profile.telegram_chat_id or None) if profile else None,
            max_chat_id=(profile.max_chat_id or None) if profile else None,
            user_id=user.pk,
        )
