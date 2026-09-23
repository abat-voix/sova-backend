from django.db import models

from sova.core.files import uuid_upload_to
from sova.core.models import TimeStampedModel


class Contract(TimeStampedModel):
    """
    Договор — минимальная сущность-документ (не путать с License, которая несёт условия лицензии).

    Даты ложатся на шаги ТЗ: sent_at (4, отправлен на подписание) → corrected_at
    (5, опциональная корректировка) → signed_at (6, подписан).

    `file` — текущий файл договора; при повторной загрузке ссылка заменяется, но прежний
    файл не пропадает — история всех загруженных файлов ведётся в `ContractFile`
    (см. `sova.interactions.services.contract_files.record_contract_file`).
    """

    file = models.FileField(
        upload_to=uuid_upload_to("contracts"),
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Файл договора",
    )
    file_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Исходное имя файла договора",
    )
    contract_number = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Номер договора",
    )
    sent_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Отправлен на подписание",
    )
    corrected_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Скорректирован перед подписанием",
    )
    signed_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Подписан",
    )

    interaction = models.ForeignKey(
        to="interactions.Interaction",
        on_delete=models.PROTECT,
        related_name="contracts",
        verbose_name="Взаимодействие",
    )

    class Meta:
        verbose_name = "Договор"
        verbose_name_plural = "Договоры"
        ordering = ["-created_at"]

    def __str__(self):
        return self.contract_number or f"Договор #{self.id}"
