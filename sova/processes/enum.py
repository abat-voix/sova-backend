from django.db.models import TextChoices


class StageInstanceContextType(TextChoices):
    """На каком уровне создан StageInstance."""

    INTERACTION = "interaction", "Взаимодействие целиком"
    IT_DIRECTION = "it_direction", "ИТ-направление"
    IT_PROGRAM = "it_program", "ИТ-программа"
    IT_PRODUCT = "it_product", "ИТ-продукт"


class WorkflowInstanceStatus(TextChoices):
    """Статус процесса workflow."""

    RUNNING = "running", "Идёт"
    COMPLETED = "completed", "Завершён"


class StageInstanceStatus(TextChoices):
    """
    Статус экземпляра этапа. «Ожидает» — этап создан, но ещё не открыт (либо возвращён откатом);
    «В работе» — этап открыт; «Завершён» — выполнены все обязательные действия.
    """

    PENDING = "pending", "Ожидает"
    IN_PROGRESS = "in_progress", "В работе"
    COMPLETED = "completed", "Завершён"


class ActionInstanceStatus(TextChoices):
    """Статус экземпляра действия."""

    PENDING = "pending", "Ожидает"
    IN_PROGRESS = "in_progress", "В работе"
    COMPLETED = "completed", "Завершено"


class RollbackMode(TextChoices):
    """Режим отката: что происходит с этапом, на который возвращается процесс."""

    RESTART = "restart", "Заново"
    LAST_ONLY = "last_only", "Только последнее обязательное действие"
