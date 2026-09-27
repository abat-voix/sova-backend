import math
from datetime import datetime, timedelta

from django.utils import timezone

from sova.notifications.enum import NotifyEvent, NotifyType
from sova.notifications.services.links import interaction_link
from sova.processes.services.deadlines import DeadlineItem

# Порядок блоков сводки: от крупного к мелкому
TYPE_ORDER = (NotifyType.WORKFLOW_DEADLINE, NotifyType.STAGE_DEADLINE, NotifyType.ACTION_DEADLINE)
OVERDUE_TITLES = {
    NotifyType.WORKFLOW_DEADLINE: "Просроченные процессы",
    NotifyType.STAGE_DEADLINE: "Просроченные этапы",
    NotifyType.ACTION_DEADLINE: "Просроченные действия",
}
TYPE_LABELS = {
    NotifyType.WORKFLOW_DEADLINE: "процесс",
    NotifyType.STAGE_DEADLINE: "этап",
    NotifyType.ACTION_DEADLINE: "действие",
}


class DeadlineMessageService:
    """Тексты и ссылки уведомлений о сроках: сводка на получателя и отдельное сообщение о пункте."""

    def render_digest(self, items: list[DeadlineItem], now: datetime, is_branded: bool = True) -> str:
        """Сводка на получателя; первая строка — тема письма (без префикса «СОВА:» при is_branded=False)."""
        overdue = [item for item in items if item.event == NotifyEvent.OVERDUE]
        reminders = [item for item in items if item.event == NotifyEvent.REMINDER]
        lines = [self._subject(f"сроки — просрочено {len(overdue)}, скоро срок {len(reminders)}", is_branded)]
        for kind in TYPE_ORDER:
            group = [item for item in overdue if item.notify_type == kind]
            if group:
                lines += ["", f"{OVERDUE_TITLES[kind]}:"]
                lines += [f"- {self._describe(item)}: {self._term(item, now)}" for item in group]
        if reminders:
            lines += ["", "Скоро срок:"]
            lines += [
                f"- {self._describe(item)} ({TYPE_LABELS[item.notify_type]}): {self._term(item, now)}" for item in reminders
            ]
        return "\n".join(lines)

    def render_single(self, item: DeadlineItem, now: datetime, is_branded: bool = True) -> str:
        """Отдельное сообщение о пункте; первая строка — тема письма (без префикса «СОВА:» при is_branded=False)."""
        title = "просрочено" if item.event == NotifyEvent.OVERDUE else "скоро срок"
        subject = self._subject(f"{title} — {TYPE_LABELS[item.notify_type]}", is_branded)
        return f"{subject}\n\n{self._describe(item)}: {self._term(item, now)}"

    def link(self, item: DeadlineItem) -> str:
        """Ссылка на взаимодействие с открытым процессом, этапом или действием пункта; без взаимодействия — пусто."""
        if item.interaction_id is None:
            return ""
        return interaction_link(
            interaction_id=item.interaction_id,
            process_id=item.workflow_instance_id,
            stage_id=item.object_id if item.notify_type == NotifyType.STAGE_DEADLINE else None,
            action_id=item.object_id if item.notify_type == NotifyType.ACTION_DEADLINE else None,
        )

    def _subject(self, subject: str, is_branded: bool) -> str:
        """Тема: «СОВА: …» для внешних каналов, где важно видеть отправителя; в интерфейсе — с заглавной буквы."""
        return f"СОВА: {subject}" if is_branded else subject[:1].upper() + subject[1:]

    def _describe(self, item: DeadlineItem) -> str:
        """Контрагент — процесс (для процесса) или этап — действие (для действия)."""
        parts = [item.counterparty]
        if item.notify_type == NotifyType.WORKFLOW_DEADLINE:
            parts.append(item.workflow_name)
        else:
            parts.append(item.stage_name)
        if item.notify_type == NotifyType.ACTION_DEADLINE:
            parts.append(item.action_name)
        return " — ".join(parts)

    def _term(self, item: DeadlineItem, now: datetime) -> str:
        """Срок и сколько дней просрочено или осталось."""
        date = timezone.localtime(item.deadline).strftime("%d.%m.%Y")
        if item.event == NotifyEvent.OVERDUE:
            return f"срок {date}, просрочено на {self._days(now - item.deadline)} дн."
        return f"срок {date}, осталось {self._days(item.deadline - now)} дн."

    def _days(self, delta: timedelta) -> int:
        """Число дней с округлением вверх: неполный день считается днём."""
        return max(1, math.ceil(delta.total_seconds() / 86400))


deadline_message_service = DeadlineMessageService()
