from django.db import models
from django.db.models.functions import Lower

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel
from sova.core.validators import validate_inn, validate_phone


class OrganizationType(models.TextChoices):
    EDUCATION = "education", "Образование"
    HEALTHCARE = "healthcare", "Здравоохранение"
    COMPANY = "company", "Компания"
    NONPROFIT = "nonprofit", "Некоммерческая организация"
    GOVERNMENT = "government", "Государственная организация"
    FACILITY = "facility", "Научный объект"
    FUNDER = "funder", "Фонд"


class Organization(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Организация, с которой взаимодействует ИТ Школа. Вид задаёт `organization_type`: вуз — это организация
    с типом «Образование».
    """

    name = models.CharField(
        max_length=255,
        verbose_name="Название организации",
    )
    name_en = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Название на английском",
    )
    short_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Краткое название",
    )
    inn = models.CharField(
        max_length=12,
        validators=[validate_inn],
        unique=True,
        null=True,
        blank=True,
        verbose_name="ИНН",
    )
    external_code = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Внешний идентификатор",
    )
    organization_type = models.CharField(
        max_length=20,
        choices=OrganizationType.choices,
        default=OrganizationType.EDUCATION,
        verbose_name="Тип организации",
    )

    # Контакты
    email = models.EmailField(
        blank=True,
        verbose_name="Email организации",
    )
    phone = models.CharField(
        max_length=50,
        validators=[validate_phone],
        blank=True,
        verbose_name="Телефон организации",
    )
    homepage_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="Сайт",
    )

    actual_same_as_legal = models.BooleanField(
        default=False,
        verbose_name="Фактический адрес совпадает с юридическим",
        help_text="Фактический адрес не хранится отдельно — берётся юридический.",
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

    normalized_text_fields = ("name", "name_en", "short_name", "external_code")

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"
        ordering = ["name"]
        # Название и код уникальны без учёта регистра: импорт сопоставляет их через iexact.
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_organization_name_ci",
                violation_error_message="Организация с таким названием уже существует.",
            ),
            models.UniqueConstraint(
                Lower("external_code"),
                name="unique_organization_external_code_ci",
                violation_error_message="Организация с таким внешним идентификатором уже существует.",
            ),
        ]

    def __str__(self):
        return self.name