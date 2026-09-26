import uuid

from django.db import models

from sova.core.text import normalize_text


class UUIDModel(models.Model):
    """Базовая модель со суррогатным uuid PK."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="ID",
    )

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    """Базовая модель с uuid PK и стандартными аудит-полями created_at/updated_at."""

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата обновления",
    )

    class Meta:
        abstract = True


class NormalizedTextFieldsMixin(models.Model):
    """
    Нормализует текстовые поля из `normalized_text_fields` (sova.core.text.normalize_text).

    Срабатывает в `full_clean` — до проверки уникальности в формах и админке — и в `save`,
    чтобы нормализованное значение попадало в БД при любом способе записи через модель.
    `QuerySet.update`/`bulk_create` модель в обход проходят — для них нормализация не выполняется.
    """

    normalized_text_fields: tuple[str, ...] = ()

    class Meta:
        abstract = True

    def normalize_text_fields(self) -> None:
        for field_name in self.normalized_text_fields:
            value = getattr(self, field_name)
            if isinstance(value, str):
                setattr(self, field_name, normalize_text(value))

    def full_clean(self, *args, **kwargs) -> None:
        self.normalize_text_fields()
        super().full_clean(*args, **kwargs)

    def save(self, *args, **kwargs) -> None:
        self.normalize_text_fields()
        super().save(*args, **kwargs)
