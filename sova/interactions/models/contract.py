from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel


class Contract(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Договор — минимальная сущность-документ (не путать с License, которая несёт условия лицензии).

    Даты ложатся на шаги ТЗ: sent_at (4, отправлен на подписание) → corrected_at
    (5, опциональная корректировка) → signed_at (6, подписан).

    Может существовать без `Interaction` ("безголовый" договор, созданный импортом реестра
    договоров) — тогда `university`/`b2c_client` хранят контрагента напрямую. После привязки к `Interaction` оба поля остаются заполненными как
    исторический снимок и должны совпадать со стороной взаимодействия (`clean()`).
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
    draft_manager_full_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="ФИО менеджера (из файла)",
        help_text="Не резолвится в User на импорте — только на привязке договора к Interaction.",
    )
    draft_status = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Статус по передаче (из файла)",
        help_text="Информационное поле, не влияет на WorkflowInstance/StageInstance.",
    )
    draft_comment = models.TextField(
        blank=True,
        verbose_name="Комментарий (из файла)",
    )

    interaction = models.ForeignKey(
        to="interactions.Interaction",
        on_delete=models.PROTECT,
        related_name="contracts",
        null=True,
        blank=True,
        verbose_name="Взаимодействие",
    )
    university = models.ForeignKey(
        to="catalog.University",
        on_delete=models.PROTECT,
        related_name="contracts",
        null=True,
        blank=True,
        verbose_name="Вуз",
    )
    b2c_client = models.ForeignKey(
        to="catalog.B2CClient",
        on_delete=models.PROTECT,
        related_name="contracts",
        null=True,
        blank=True,
        verbose_name="B2C-клиент",
    )

    normalized_text_fields = ("contract_number", "draft_manager_full_name", "draft_status")

    class Meta:
        verbose_name = "Договор"
        verbose_name_plural = "Договоры"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(university__isnull=False, b2c_client__isnull=True)
                    | Q(university__isnull=True, b2c_client__isnull=False)
                ),
                name="contract_exactly_one_counterparty",
            ),
        ]

    def clean(self):
        if self.interaction_id is None:
            return
        if (
            self.university_id != self.interaction.university_id
            or self.b2c_client_id != self.interaction.b2c_client_id
        ):
            raise ValidationError(
                {"interaction": "Контрагент договора не совпадает с контрагентом взаимодействия."}
            )

    def save(self, *args, **kwargs):
        # Договор, привязанный к Interaction, хранит снимок его контрагента.
        if self.interaction_id is not None:
            self.university_id = self.interaction.university_id
            self.b2c_client_id = self.interaction.b2c_client_id
        super().save(*args, **kwargs)

    def __str__(self):
        return self.contract_number or f"Договор #{self.id}"
