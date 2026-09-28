from django.contrib.postgres.fields import ArrayField
from django.db import models

from sova.catalog.enum import ContactChannel
from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel


class AbstractContactAffiliation(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Связь человека с организацией: должность и способы связи относятся к паре «человек + организация».

    У пары одна связь, и она либо есть, либо её нет: активность — только у человека (`ContactPerson.is_active`).
    Человек ушёл из организации — связь удаляют (`ContactAffiliationService.delete`), вернулся — создают заново.

    Конкретные связи — `OrganizationContact`, `B2CClientContact`, `VendorContact`; выбирать модель по типу
    организации — задача `ContactAffiliationService`, а не вызывающего кода.
    """

    position = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Должность",
    )
    preferred_channels = ArrayField(
        models.CharField(max_length=20, choices=ContactChannel.choices),
        default=list,
        blank=True,
        verbose_name="Способы связи",
    )

    normalized_text_fields = ("position",)

    class Meta:
        abstract = True

    @staticmethod
    def pair_constraints(organization_field: str, prefix: str) -> list[models.BaseConstraint]:
        """Одна связь у пары «человек + организация»."""
        return [
            models.UniqueConstraint(
                fields=["contact", organization_field],
                name=f"unique_{prefix}",
                violation_error_message="Это контактное лицо уже связано с этой организацией.",
            ),
        ]
