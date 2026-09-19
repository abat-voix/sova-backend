from django.db import models

from sova.crm.models.base import TimeStampedModel


class Contract(TimeStampedModel):
    """
    Договор — минимальная сущность-документ (не путать с License, которая несёт условия лицензии).

    Даты ложатся на шаги ТЗ: sent_at (4, отправлен на подписание) → corrected_at
    (5, опциональная корректировка) → signed_at (6, подписан).
    """

    file = models.FileField(
        upload_to="contracts/%Y/%m/",
        null=True,
        blank=True,
        verbose_name="Файл договора",
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

    contact = models.ForeignKey(
        to="crm.Contact",
        on_delete=models.PROTECT,
        related_name="contracts",
        verbose_name="Сделка",
    )

    class Meta:
        verbose_name = "Договор"
        verbose_name_plural = "Договоры"
        ordering = ["-created_at"]

    def __str__(self):
        return self.contract_number or f"Договор #{self.id}"
