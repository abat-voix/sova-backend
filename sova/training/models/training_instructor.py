from django.db import models
from django.db.models import Q

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel
from sova.core.validators import validate_phone
from sova.training.enum import AcademicDegree, AcademicTitle


class TrainingInstructor(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Преподаватель, который ведёт потоки от организации или B2C-клиента — место работы ровно одно из двух.

    Не путать с `OrganizationContact`: те — контакты для договора и коммуникации.
    """

    last_name = models.CharField(max_length=255, verbose_name="Фамилия")
    first_name = models.CharField(max_length=255, verbose_name="Имя")
    middle_name = models.CharField(max_length=255, blank=True, verbose_name="Отчество")
    email = models.EmailField(blank=True, verbose_name="Email")
    phone = models.CharField(max_length=50, blank=True, validators=[validate_phone], verbose_name="Телефон")
    telegram = models.CharField(max_length=64, blank=True, verbose_name="Telegram")

    organization = models.ForeignKey(
        to="catalog.Organization",
        on_delete=models.PROTECT,
        related_name="training_instructors",
        null=True,
        blank=True,
        verbose_name="Организация",
    )
    b2c_client = models.ForeignKey(
        to="catalog.B2CClient",
        on_delete=models.PROTECT,
        related_name="training_instructors",
        null=True,
        blank=True,
        verbose_name="B2C-клиент",
    )
    department = models.CharField(max_length=255, blank=True, verbose_name="Подразделение")
    position = models.CharField(max_length=255, blank=True, verbose_name="Должность")

    academic_degree = models.CharField(
        max_length=20,
        choices=AcademicDegree.choices,
        default=AcademicDegree.NONE,
        verbose_name="Учёная степень",
    )
    academic_title = models.CharField(
        max_length=20,
        choices=AcademicTitle.choices,
        default=AcademicTitle.NONE,
        verbose_name="Учёное звание",
    )
    teaching_experience_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Стаж преподавания, лет",
    )
    education = models.TextField(blank=True, verbose_name="Образование")

    directions = models.ManyToManyField(
        to="catalog.Direction",
        related_name="training_instructors",
        blank=True,
        verbose_name="Направления",
    )
    programs = models.ManyToManyField(
        to="catalog.Program",
        related_name="training_instructors",
        blank=True,
        verbose_name="Программы",
    )

    lms_external_id = models.CharField(max_length=255, blank=True, verbose_name="ID в LMS")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    comment = models.TextField(blank=True, verbose_name="Комментарий")

    normalized_text_fields = ("last_name", "first_name", "middle_name", "department", "position", "phone")

    class Meta:
        verbose_name = "Преподаватель"
        verbose_name_plural = "Преподаватели"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(organization__isnull=False, b2c_client__isnull=True)
                    | Q(organization__isnull=True, b2c_client__isnull=False)
                ),
                name="training_instructor_exactly_one_organization",
            ),
            models.UniqueConstraint(
                fields=["lms_external_id"],
                condition=~Q(lms_external_id=""),
                name="unique_training_instructor_lms_id",
            ),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    @property
    def employer(self):
        """Где работает преподаватель: организация или B2C-клиент."""
        return self.organization or self.b2c_client
