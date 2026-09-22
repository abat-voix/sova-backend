from django.db.models import TextChoices


class ReportType(TextChoices):
    """Тип отчёта. B2C подключается отдельным типом на том же механизме."""

    INTERACTIONS = "interactions", "Взаимодействия с вузами"


class ReportFormat(TextChoices):
    """Формат выгрузки отчёта."""

    XLSX = "xlsx", "XLSX"
    XLS = "xls", "XLS"
    PDF = "pdf", "PDF"
    JSON = "json", "JSON"


class ReportJobStatus(TextChoices):
    """Состояние задания на построение отчёта."""

    QUEUED = "queued", "В очереди"
    RUNNING = "running", "Строится"
    READY = "ready", "Готов"
    FAILED = "failed", "Ошибка"


class ReportOrdering(TextChoices):
    """Допустимые порядки сортировки строк отчёта."""

    CREATED_AT = "created_at", "По дате создания (старые сначала)"
    CREATED_AT_DESC = "-created_at", "По дате создания (новые сначала)"
    UNIVERSITY = "university", "По названию вуза"
    RESPONSIBLE = "responsible", "По ответственному"
