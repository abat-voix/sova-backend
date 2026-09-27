from django.conf import settings
from django.db import models

from sova.core.files import uuid_upload_to
from sova.core.models import TimeStampedModel
from sova.training.enum import QualificationDocumentType, QualificationKind


class TrainingInstructorQualification(TimeStampedModel):
    """Запись о подготовке преподавателя: обучение преподавателей или повышение квалификации по программе."""

    instructor = models.ForeignKey(
        to="training.TrainingInstructor",
        on_delete=models.CASCADE,
        related_name="qualifications",
        verbose_name="Преподаватель",
    )
    kind = models.CharField(max_length=20, choices=QualificationKind.choices, verbose_name="Вид подготовки")
    program = models.ForeignKey(
        to="catalog.Program",
        on_delete=models.PROTECT,
        related_name="training_instructor_qualifications",
        verbose_name="Программа",
    )
    interaction = models.ForeignKey(
        to="interactions.Interaction",
        on_delete=models.SET_NULL,
        related_name="training_instructor_qualifications",
        null=True,
        blank=True,
        verbose_name="Взаимодействие",
    )
    completed_at = models.DateField(verbose_name="Дата завершения")
    document_type = models.CharField(
        max_length=20,
        choices=QualificationDocumentType.choices,
        blank=True,
        verbose_name="Тип документа",
    )
    document_number = models.CharField(max_length=255, blank=True, verbose_name="Номер документа")
    document_file = models.FileField(
        upload_to=uuid_upload_to("training/qualifications"),
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Файл документа",
    )
    valid_until = models.DateField(null=True, blank=True, verbose_name="Действует до")
    comment = models.TextField(blank=True, verbose_name="Комментарий")
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name="Кто создал",
    )

    class Meta:
        verbose_name = "Подготовка преподавателя"
        verbose_name_plural = "Подготовка преподавателей"
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.instructor} — {self.program} ({self.get_kind_display()})"
