from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel


class ContactPerson(NormalizedTextFieldsMixin, TimeStampedModel):
    """Контактное лицо со стороны вуза или B2C-клиента-юрлица. Контрагент — ровно один из двух."""

    full_name = models.CharField(
        max_length=255,
        verbose_name="ФИО",
    )
    position = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Должность",
    )
    email = models.EmailField(
        blank=True,
        verbose_name="Email",
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Телефон",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    university = models.ForeignKey(
        to="catalog.University",
        on_delete=models.CASCADE,
        related_name="contact_persons",
        null=True,
        blank=True,
        verbose_name="Вуз",
    )
    b2c_client = models.ForeignKey(
        to="catalog.B2CClient",
        on_delete=models.CASCADE,
        related_name="contact_persons",
        null=True,
        blank=True,
        verbose_name="B2C-клиент",
    )

    normalized_text_fields = ("full_name", "position", "phone")

    class Meta:
        verbose_name = "Контактное лицо"
        verbose_name_plural = "Контактные лица"
        ordering = ["full_name"]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(university__isnull=False, b2c_client__isnull=True)
                    | Q(university__isnull=True, b2c_client__isnull=False)
                ),
                name="contact_person_exactly_one_counterparty",
            ),
            # ФИО уникально у контрагента без учёта регистра: импорт сопоставляет его через iexact.
            models.UniqueConstraint(
                F("university"),
                Lower("full_name"),
                name="unique_university_contact_name",
                violation_error_message="Контактное лицо с таким ФИО у этого вуза уже существует.",
            ),
            models.UniqueConstraint(
                F("b2c_client"),
                Lower("full_name"),
                name="unique_b2c_client_contact_name",
                violation_error_message="Контактное лицо с таким ФИО у этого B2C-клиента уже существует.",
            ),
        ]

    def __str__(self):
        return self.full_name
