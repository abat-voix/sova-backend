from django.conf import settings
from django.db import models

from sova.core.models import TimeStampedModel


class TrainingStreamInstructor(TimeStampedModel):
    """Назначение преподавателя на поток."""

    stream = models.ForeignKey(
        to="training.TrainingStream",
        on_delete=models.CASCADE,
        related_name="instructor_links",
        verbose_name="Поток",
    )
    instructor = models.ForeignKey(
        to="training.TrainingInstructor",
        on_delete=models.PROTECT,
        related_name="stream_links",
        verbose_name="Преподаватель",
    )
    assigned_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name="Кто назначил",
    )

    class Meta:
        verbose_name = "Преподаватель потока"
        verbose_name_plural = "Преподаватели потоков"
        constraints = [
            models.UniqueConstraint(fields=["stream", "instructor"], name="unique_training_stream_instructor"),
        ]

    def __str__(self):
        return f"{self.stream} — {self.instructor}"
