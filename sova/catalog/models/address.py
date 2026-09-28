from django.db import models

from sova.core.models import TimeStampedModel


class AbstractAddress(TimeStampedModel):
    """
    Открытые части адреса, общие для организации и B2C-клиента: страна, регион и город — по ним фильтруют и ищут.

    Улица, дом, помещение и индекс задаёт наследник: у организации они публичные, у физлица — персональные данные
    и хранятся зашифрованными.
    """

    country_code = models.CharField(
        max_length=2,
        blank=True,
        db_index=True,
        verbose_name="Код страны (ISO 3166-1 alpha-2)",
    )
    region = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Регион",
    )
    city = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        verbose_name="Город / населённый пункт",
    )

    class Meta:
        abstract = True
