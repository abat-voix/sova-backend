from typing import NamedTuple

from sova.catalog.schemas import ImportRowWarning
from sova.training.models import TrainingApplication


class LearnerImportResult(NamedTuple):
    """Итог загрузки файла «Пользователи»: обучающиеся и заявка потока (если поток выбран и кого-то добавили)."""

    created: int
    updated: int
    warnings: list[ImportRowWarning]
    application: TrainingApplication | None
