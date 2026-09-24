import logging
from dataclasses import replace

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from sova.notifications.enum import NOTIFY_TYPE_GROUPS, NotificationChannel
from sova.notifications.models import NotifySettings
from sova.notifications.services.message import Message
from sova.notifications.tasks import send_event_notification

logger = logging.getLogger("django")

# Префикс темы во внешних каналах — как у уведомлений о сроках: там важно видеть отправителя
BRAND_PREFIX = "СОВА: "


class EventNotificationService:
    """
    Отправка событийного уведомления по настройкам его типа.

    Код события передаёт тип, готовое сообщение и кандидатов на роли; кому и по каким каналам слать, решает
    строка NotifySettings. Отправка — после фиксации транзакции, в фоне; без повторов и без журнала.
    """

    def notify(
        self,
        notify_type: str,
        message: Message,
        responsible: AbstractBaseUser | None = None,
        head: AbstractBaseUser | None = None,
        actor: AbstractBaseUser | None = None,
    ) -> None:
        """Ставит отправку после фиксации транзакции; выключенный тип, нет строки или получателей — ничего."""
        rule = NotifySettings.objects.filter(notify_type=notify_type).first()
        if rule is None:
            logger.warning("Нет NotifySettings для «%s» — уведомление не отправлено", notify_type)
            return
        if not rule.is_enabled:
            return
        recipients = self._recipients(rule=rule, responsible=responsible, head=head, actor=actor)
        if not recipients:
            return
        message = replace(message, kind=NOTIFY_TYPE_GROUPS[notify_type])
        user_ids = [user.pk for user in recipients]
        for channels, text in self._batches(channels=rule.channels(), text=message.text):
            # robust: сбой брокера только логируется — событие уже зафиксировано, уведомление побочное.
            # Не partial: при сбое Django логирует callback.__qualname__, которого у partial нет
            def enqueue(channels: list[str] = channels, text: str = text) -> None:
                send_event_notification.delay(
                    user_ids=user_ids,
                    channels=channels,
                    text=text,
                    kind=message.kind,
                    link=message.link,
                )

            transaction.on_commit(enqueue, robust=True)

    def _recipients(
        self,
        rule: NotifySettings,
        responsible: AbstractBaseUser | None,
        head: AbstractBaseUser | None,
        actor: AbstractBaseUser | None,
    ) -> list[AbstractBaseUser]:
        """Получатели по флагам правила: без пустых, неактивных, инициатора и повторов."""
        candidates = []
        if rule.is_notify_responsible:
            candidates.append(responsible)
        if rule.is_notify_head:
            candidates.append(head)
        users: dict[int, AbstractBaseUser] = {}
        for user in candidates:
            if user is None or not user.is_active or (actor is not None and user.pk == actor.pk):
                continue
            users.setdefault(user.pk, user)
        return list(users.values())

    def _batches(self, channels: list[NotificationChannel], text: str) -> list[tuple[list[str], str]]:
        """Колокольчик — текст как есть; внешние каналы — одной группой с префиксом «СОВА:»."""
        batches: list[tuple[list[str], str]] = []
        if NotificationChannel.SYSTEM in channels:
            batches.append(([NotificationChannel.SYSTEM], text))
        external = [channel for channel in channels if channel != NotificationChannel.SYSTEM]
        if external:
            batches.append((external, BRAND_PREFIX + text))
        return batches


event_notification_service = EventNotificationService()
