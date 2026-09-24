from django.db.models import TextChoices


class NotificationChannel(TextChoices):
    """Канал доставки уведомления."""

    EMAIL = "email", "Email"
    TELEGRAM = "telegram", "Telegram"
    MAX = "max", "MAX"
    SYSTEM = "system", "В системе"


class NotificationKind(TextChoices):
    """Группа уведомления в системе: по ней фронт строит фильтры и иконки."""

    DEADLINE = "deadline", "Сроки"
    ASSIGNMENT = "assignment", "Назначения"
    SYSTEM = "system", "Системные"


# Имя иконки lucide для группы: фронт берёт его из API, неизвестное заменяет колокольчиком
NOTIFICATION_KIND_ICONS: dict[str, str] = {
    NotificationKind.DEADLINE: "calendar-clock",
    NotificationKind.ASSIGNMENT: "user-check",
    NotificationKind.SYSTEM: "bell",
}


class NotifyType(TextChoices):
    """Тип уведомления: ключ строки NotifySettings."""

    ACTION_DEADLINE = "action_deadline", "Сроки действия"
    STAGE_DEADLINE = "stage_deadline", "Сроки этапа"
    WORKFLOW_DEADLINE = "workflow_deadline", "Сроки процесса"
    KAM_ASSIGNED = "kam_assigned", "Назначение КАМа"


# Типы, которые обрабатывает задача notify_deadlines; только они пишутся в журнал DeadlineDelivery
DEADLINE_NOTIFY_TYPES = (NotifyType.ACTION_DEADLINE, NotifyType.STAGE_DEADLINE, NotifyType.WORKFLOW_DEADLINE)

# Группа колокольчика для типа уведомления
NOTIFY_TYPE_GROUPS: dict[str, str] = {
    NotifyType.ACTION_DEADLINE: NotificationKind.DEADLINE,
    NotifyType.STAGE_DEADLINE: NotificationKind.DEADLINE,
    NotifyType.WORKFLOW_DEADLINE: NotificationKind.DEADLINE,
    NotifyType.KAM_ASSIGNED: NotificationKind.ASSIGNMENT,
}


class NotifyEvent(TextChoices):
    """Событие по сроку: срок прошёл или скоро наступит."""

    OVERDUE = "overdue", "Просрочка"
    REMINDER = "reminder", "Предупреждение"


class HeadMode(TextChoices):
    """Кого считать руководителем при уведомлении."""

    ASSIGNED_BY = "assigned_by", "Назначивший руководитель"
    ALL_HEADS = "all_heads", "Все руководители"


class DeliveryMode(TextChoices):
    """Как доставлять уведомления получателю."""

    DIGEST = "digest", "Сводкой"
    SEPARATE = "separate", "Отдельными сообщениями"
