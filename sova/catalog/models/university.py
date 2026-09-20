from django.db import models

from sova.core.models import TimeStampedModel


class University(TimeStampedModel):
    """Вуз — учебное заведение, с которым взаимодействует ИТ Школа."""

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Название вуза",
    )
    inn = models.CharField(
        max_length=12,
        unique=True,
        null=True,
        blank=True,
        verbose_name="ИНН",
    )
    external_code = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Внешний идентификатор",
    )
    email = models.EmailField(
        blank=True,
        verbose_name="Email вуза",
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Телефон вуза",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    class Meta:
        verbose_name = "Вуз"
        verbose_name_plural = "Вузы"
        ordering = ["name"]

    def __str__(self):
        return self.name
