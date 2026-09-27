from django.conf import settings
from django.db import models
from django.db.models import F, Q

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel
from sova.training.enum import TrainingStreamStatus


class TrainingStream(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Поток обучения по программе взаимодействия; номер потока — его `id`.

    У программы взаимодействия может быть несколько потоков. Программа, взаимодействие и контрагент выводятся через
    `interaction_program` и не дублируются. Создаётся возможностью `training.create` после подписания договора.
    """

    interaction_program = models.ForeignKey(
        to="interactions.InteractionProgram",
        on_delete=models.PROTECT,
        related_name="streams",
        verbose_name="Программа взаимодействия",
    )
    name = models.CharField(
        max_length=255,
        verbose_name="Название",
    )
    starts_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Начало обучения",
    )
    ends_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Окончание обучения",
    )
    status = models.CharField(
        max_length=20,
        choices=TrainingStreamStatus.choices,
        default=TrainingStreamStatus.DRAFT,
        verbose_name="Статус",
    )
    instructors = models.ManyToManyField(
        to="training.TrainingInstructor",
        through="training.TrainingStreamInstructor",
        related_name="streams",
        blank=True,
        verbose_name="Преподаватели",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name="Кто создал",
    )

    normalized_text_fields = ("name",)

    class Meta:
        verbose_name = "Поток обучения"
        verbose_name_plural = "Потоки обучения"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(starts_at__isnull=True) | Q(ends_at__isnull=True) | Q(ends_at__gte=F("starts_at")),
                name="training_stream_dates_order",
            ),
        ]

    def __str__(self):
        return self.name
