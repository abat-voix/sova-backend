from dataclasses import dataclass, field
from datetime import datetime

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import F
from django.utils import timezone

from sova.notifications.enum import NOTIFY_TYPE_GROUPS, DeliveryMode, NotificationChannel, NotifyEvent
from sova.notifications.models import DeadlineDelivery, NotifySettings
from sova.notifications.services.deadline_messages import deadline_message_service
from sova.notifications.services.message import Message
from sova.notifications.services.notifier import notification_service
from sova.processes.services.deadlines import DeadlineItem

_JournalKey = tuple[str, str, object, datetime, int, str]
_Due = tuple[NotifySettings, DeadlineItem, AbstractBaseUser, NotificationChannel]


@dataclass
class _Message:
    """Одно сообщение получателю по одному каналу: сводка или отдельный пункт."""

    recipient: AbstractBaseUser
    channel: NotificationChannel
    mode: str
    items: list[DeadlineItem] = field(default_factory=list)


class DeadlineDispatchService:
    """
    Доставка уведомлений о сроках по правилам NotifySettings.

    Отсекает тройки (пункт, получатель, канал), уже доставленные по журналу DeadlineDelivery;
    повторяет просрочку раз в repeat_every_days календарных дней; предупреждение — один раз. Журнал
    пишется по каждому каналу отдельно, поэтому недоставленное повторится на следующем запуске только
    по упавшему каналу.
    """

    def dispatch(self, items: list[DeadlineItem], now: datetime) -> dict:
        """Отправляет причитающиеся сообщения и возвращает статистику."""
        rules = NotifySettings.objects.in_bulk(field_name="notify_type")
        journal = self._journal(items=items)
        is_weekend = timezone.localtime(now).weekday() >= 5

        due: list[_Due] = []
        for item in items:
            rule = rules.get(item.notify_type)
            if rule is None or (is_weekend and rule.is_skip_weekends):
                continue
            for recipient in item.recipients:
                for channel in rule.channels():
                    row = journal.get(self._key(item=item, recipient_id=recipient.pk, channel=channel))
                    if self._is_due(rule=rule, item=item, row=row, now=now):
                        due.append((rule, item, recipient, channel))

        messages = self._build_messages(due=due)
        stats = {"items": len(items), "messages": len(messages), "sent": 0, "failed": 0}
        for message in messages:
            results = notification_service.send(
                recipient=message.recipient,
                message=Message(
                    text=self._render(message=message, now=now),
                    # Все пункты сообщения — типы сроков, группа у них одна
                    kind=NOTIFY_TYPE_GROUPS[message.items[0].notify_type],
                    link=self._link(message=message),
                ),
                channels=(message.channel,),
            )
            if any(result.success for result in results):
                self._record(message=message, journal=journal, now=now)
                stats["sent"] += 1
            else:
                stats["failed"] += 1
        return stats

    def _key(self, item: DeadlineItem, recipient_id: int, channel: str) -> _JournalKey:
        """Ключ записи журнала — как у UniqueConstraint модели."""
        return (item.notify_type, item.event, item.object_id, item.deadline, recipient_id, channel)

    def _journal(self, items: list[DeadlineItem]) -> dict[_JournalKey, DeadlineDelivery]:
        """Записи журнала по объектам пунктов — одним запросом."""
        rows = DeadlineDelivery.objects.filter(object_id__in={item.object_id for item in items})
        return {
            (row.notify_type, row.event, row.object_id, row.deadline, row.recipient_id, row.channel): row
            for row in rows
        }

    def _is_due(
        self,
        rule: NotifySettings,
        item: DeadlineItem,
        row: DeadlineDelivery | None,
        now: datetime,
    ) -> bool:
        """Нужно ли слать пару: впервые — да; предупреждение — один раз; просрочка — по repeat_every_days."""
        if row is None:
            return True
        if item.event == NotifyEvent.REMINDER or rule.repeat_every_days is None:
            return False
        # Календарные дни, а не timedelta: ежедневный запуск в 09:00:01 после отправки в 09:00:03
        # накануне должен считаться «прошли сутки»
        elapsed = timezone.localdate(now) - timezone.localdate(row.last_sent_at)
        return elapsed.days >= rule.repeat_every_days

    def _record(self, message: _Message, journal: dict[_JournalKey, DeadlineDelivery], now: datetime) -> None:
        """Отмечает доставку: новые пары — вставкой, повторы — счётчиком."""
        created: list[DeadlineDelivery] = []
        repeated: list = []
        for item in message.items:
            row = journal.get(self._key(item=item, recipient_id=message.recipient.pk, channel=message.channel))
            if row is None:
                created.append(
                    DeadlineDelivery(
                        notify_type=item.notify_type,
                        event=item.event,
                        channel=message.channel,
                        object_id=item.object_id,
                        deadline=item.deadline,
                        recipient=message.recipient,
                        last_sent_at=now,
                    ),
                )
            else:
                repeated.append(row.pk)
        # ignore_conflicts: параллельный запуск мог уже записать ту же пару
        DeadlineDelivery.objects.bulk_create(created, ignore_conflicts=True)
        DeadlineDelivery.objects.filter(pk__in=repeated).update(
            last_sent_at=now,
            send_count=F("send_count") + 1,
        )

    def _build_messages(self, due: list[_Due]) -> list[_Message]:
        """
        Сводка — одна на (получатель, канал); отдельный режим — сообщение на (пункт, получатель, канал).

        В колокольчик всегда отдельными сообщениями: у каждого пункта своя ссылка, а сводке одну ссылку не дать.
        """
        messages: list[_Message] = []
        digests: dict[tuple[int, str], _Message] = {}
        for rule, item, recipient, channel in due:
            if rule.delivery_mode == DeliveryMode.SEPARATE or channel == NotificationChannel.SYSTEM:
                messages.append(
                    _Message(recipient=recipient, channel=channel, mode=DeliveryMode.SEPARATE, items=[item]),
                )
                continue
            digest = digests.setdefault(
                (recipient.pk, channel),
                _Message(recipient=recipient, channel=channel, mode=DeliveryMode.DIGEST),
            )
            digest.items.append(item)
        return messages + list(digests.values())

    def _link(self, message: _Message) -> str:
        """Ссылка на объект для отдельного сообщения; у сводки ссылки нет."""
        if message.mode == DeliveryMode.SEPARATE:
            return deadline_message_service.link(item=message.items[0])
        return ""

    def _render(self, message: _Message, now: datetime) -> str:
        """Текст сообщения по режиму доставки; в колокольчике префикс «СОВА:» не нужен — сообщение уже внутри СОВА."""
        is_branded = message.channel != NotificationChannel.SYSTEM
        if message.mode == DeliveryMode.SEPARATE:
            return deadline_message_service.render_single(item=message.items[0], now=now, is_branded=is_branded)
        return deadline_message_service.render_digest(items=message.items, now=now, is_branded=is_branded)


deadline_dispatch_service = DeadlineDispatchService()
