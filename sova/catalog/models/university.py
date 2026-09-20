from django.db import models

from sova.core.models import TimeStampedModel


class InstitutionType(models.TextChoices):
    EDUCATION = "education", "Образование"
    HEALTHCARE = "healthcare", "Здравоохранение"
    COMPANY = "company", "Компания"
    ARCHIVE = "archive", "Архив"
    NONPROFIT = "nonprofit", "Некоммерческая организация"
    GOVERNMENT = "government", "Государственная организация"
    FACILITY = "facility", "Научный объект"
    FUNDER = "funder", "Фонд"
    OTHER = "other", "Другое"


class University(TimeStampedModel):
    """Вуз — учебное заведение, с которым взаимодействует ИТ Школа."""

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Название вуза",
    )
    name_en = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Название на английском",
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
    institution_type = models.CharField(
        max_length=20,
        choices=InstitutionType.choices,
        default=InstitutionType.EDUCATION,
        verbose_name="Тип организации",
    )

    # Контакты
    email = models.EmailField(
        blank=True,
        verbose_name="Email вуза",
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Телефон вуза",
    )
    homepage_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="Сайт",
    )

    # География
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
        verbose_name="Город",
    )
    lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Широта",
    )
    lon = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Долгота",
    )

    # Наукометрия
    works_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество публикаций",
    )
    cited_by_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Количество цитирований",
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