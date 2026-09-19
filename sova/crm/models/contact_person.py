from django.db import models
from django.db.models import Q

from sova.crm.models.base import TimeStampedModel


class ContactPerson(TimeStampedModel):
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
        to="crm.University",
        on_delete=models.CASCADE,
        related_name="contact_persons",
        null=True,
        blank=True,
        verbose_name="Вуз",
    )
    b2c_client = models.ForeignKey(
        to="crm.B2CClient",
        on_delete=models.CASCADE,
        related_name="contact_persons",
        null=True,
        blank=True,
        verbose_name="B2C-клиент",
    )

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
            models.UniqueConstraint(
                fields=["university", "full_name"],
                name="unique_university_contact_name",
            ),
            models.UniqueConstraint(
                fields=["b2c_client", "full_name"],
                name="unique_b2c_client_contact_name",
            ),
        ]

    def __str__(self):
        return self.full_name
