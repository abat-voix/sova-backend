from django.db import models

from sova.core.models import TimeStampedModel


class TrainingApplicationLearner(TimeStampedModel):
    """
    Участник заявки. Оплата — только факт `is_paid`: оплаченный участник действующей заявки с потоком зачислен
    (см. `sova.training.services.enrollment`). Ошибочную отметку снимают, выставляя `is_paid=False`.
    """

    application = models.ForeignKey(
        to="training.TrainingApplication",
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name="Заявка",
    )
    learner = models.ForeignKey(
        to="training.Learner",
        on_delete=models.PROTECT,
        related_name="participations",
        verbose_name="Обучающийся",
    )
    is_paid = models.BooleanField(
        default=False,
        verbose_name="Оплачено",
    )

    class Meta:
        verbose_name = "Участник заявки"
        verbose_name_plural = "Участники заявок"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["application", "learner"], name="unique_training_application_learner"),
        ]

    def __str__(self):
        return f"{self.application} — {self.learner}"
