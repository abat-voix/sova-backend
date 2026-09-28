from django.db import models

from sova.core.models import TimeStampedModel


class B2CClient(TimeStampedModel):
    """B2C-клиент — физическое лицо. Компании и вузы — это организации (`Organization`)."""

    full_name = models.CharField(
        max_length=255,
        verbose_name="ФИО",
    )
    inn = models.CharField(
        max_length=12,
        null=True,
        blank=True,
        verbose_name="ИНН",
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

    class Meta:
        verbose_name = "B2C-клиент"
        verbose_name_plural = "B2C-клиенты"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name
