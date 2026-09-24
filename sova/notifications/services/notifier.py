import logging
from collections.abc import Iterable
from dataclasses import dataclass

from django.contrib.auth.models import AbstractBaseUser

from sova.notifications.enum import NotificationChannel
from sova.notifications.services.channels import (
    EmailChannelSender,
    MaxChannelSender,
    SystemChannelSender,
    TelegramChannelSender,
)
from sova.notifications.services.channels.base import NotificationChannelSender
from sova.notifications.services.message import Message
from sova.notifications.services.recipient import Recipient

logger = logging.getLogger("django")

CHANNEL_RECIPIENT_FIELD: dict[NotificationChannel, str] = {
    NotificationChannel.EMAIL: "email",
    NotificationChannel.TELEGRAM: "telegram_chat_id",
    NotificationChannel.MAX: "max_chat_id",
    NotificationChannel.SYSTEM: "user_id",
}


@dataclass
class NotificationResult:
    """Результат попытки отправки уведомления одному получателю по одному каналу."""

    recipient: Recipient
    channel: NotificationChannel
    success: bool


class NotificationService:
    """Универсальная отправка уведомлений по email, Telegram, MAX и в систему."""

    def __init__(self) -> None:
        self._senders: dict[NotificationChannel, NotificationChannelSender] = {
            NotificationChannel.EMAIL: EmailChannelSender(),
            NotificationChannel.TELEGRAM: TelegramChannelSender(),
            NotificationChannel.MAX: MaxChannelSender(),
            NotificationChannel.SYSTEM: SystemChannelSender(),
        }

    def send(
        self,
        recipient: AbstractBaseUser | Recipient | Iterable[AbstractBaseUser | Recipient],
        message: str | Message,
        channels: Iterable[NotificationChannel] | None = None,
    ) -> list[NotificationResult]:
        """
        Отправляет message получателю(ям) по всем каналам, для которых есть адрес.

        message — строка или Message; строка становится Message системной группы
        без ссылки. recipient — один или несколько User/Recipient. channels сужает набор
        каналов (по умолчанию — все). Получатель без адреса для канала —
        канал для него молча пропускается. Ошибка одного канала логируется и
        не прерывает отправку остальным получателям/каналам.
        """
        if isinstance(message, str):
            message = Message(text=message)
        recipients = self._as_recipients(recipient)
        channel_list = list(channels) if channels is not None else list(NotificationChannel)

        results: list[NotificationResult] = []
        for single_recipient in recipients:
            for channel in channel_list:
                results.extend(
                    self._send_to_channel(
                        recipient=single_recipient,
                        channel=channel,
                        message=message,
                    ),
                )
        return results


    def _as_recipients(
        self,
        recipient: AbstractBaseUser | Recipient | Iterable[AbstractBaseUser | Recipient],
    ) -> list[Recipient]:
        """Приводит recipient к списку Recipient, конвертируя User через Recipient.for_user()."""
        items: Iterable[AbstractBaseUser | Recipient]
        if isinstance(recipient, (Recipient, AbstractBaseUser)):
            items = [recipient]
        else:
            items = recipient
        return [item if isinstance(item, Recipient) else Recipient.for_user(item) for item in items]

    def _send_to_channel(
        self,
        recipient: Recipient,
        channel: NotificationChannel,
        message: Message,
    ) -> list[NotificationResult]:
        """Отправляет message получателю по одному каналу, если у него есть адрес."""
        target = getattr(recipient, CHANNEL_RECIPIENT_FIELD[channel])
        if not target:
            return []
        try:
            success = self._senders[channel].send(target=target, message=message)
        except Exception:
            # Страховка сверху отправителей канала: даже баг в конкретном send() не должен
            # прерывать рассылку остальным каналам/получателям.
            logger.exception("Необработанная ошибка канала %s для получателя %s", channel, target)
            success = False
        return [NotificationResult(recipient=recipient, channel=channel, success=success)]


notification_service = NotificationService()
