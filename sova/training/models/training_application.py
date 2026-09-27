from django.conf import settings
from django.db import models

from sova.core.models import TimeStampedModel
from sova.training.enum import TrainingApplicationStatus


class TrainingApplication(TimeStampedModel):
    """
    Заявка на поток; в ней может быть несколько обучающихся (`TrainingApplicationLearner`).

    Создаётся вручную по потоку или загрузкой файла «Пользователи» с выбранным потоком. Заявку с оплатившими
    участниками не удаляют — её отменяют.
    """

    stream = models.ForeignKey(
        to="training.TrainingStream",
        on_delete=models.PROTECT,
        related_name="applications",
        verbose_name="Поток",
    )
    status = models.CharField(
        max_length=20,
        choices=TrainingApplicationStatus.choices,
        default=TrainingApplicationStatus.NEW,
        verbose_name="Статус",
    )
    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name="Кто создал",
    )
    learners = models.ManyToManyField(
        to="training.Learner",
        through="training.TrainingApplicationLearner",
        related_name="applications",
        blank=True,
        verbose_name="Обучающиеся",
    )

    class Meta:
        verbose_name = "Заявка на обучение"
        verbose_name_plural = "Заявки на обучение"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заявка на {self.stream} от {self.created_at:%d.%m.%Y}"
