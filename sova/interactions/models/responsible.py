from django.conf import settings
from django.db import models

from sova.core.models import UUIDModel


class Responsible(UUIDModel):
    """
    Назначение ответственного менеджера (КАМ) на взаимодействие, с историей.

    Привязана к Interaction (взаимодействию), а не к University/B2CClient целиком — у каждого взаимодействия
    своя история ответственных, параллельные взаимодействия одного контрагента могут вести
    разных людей. Действующих КАМов у взаимодействия может быть несколько, но один менеджер
    не может быть назначен на одно взаимодействие дважды одновременно.
    """

    assigned_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Назначен",
    )
    unassigned_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Снят с назначения",
    )

    interaction = models.ForeignKey(
        to="interactions.Interaction",
        on_delete=models.CASCADE,
        related_name="responsibles",
        verbose_name="Взаимодействие",
    )
    manager = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="responsibles_as_manager",
        verbose_name="Ответственный менеджер",
    )
    assigned_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="responsibles_as_assigned_by",
        null=True,
        blank=True,
        verbose_name="Назначил",
    )

    class Meta:
        verbose_name = "Ответственный"
        verbose_name_plural = "Ответственные"
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "manager"],
                condition=models.Q(unassigned_at__isnull=True),
                name="one_active_responsible_per_manager",
            ),
        ]

    def __str__(self):
        return f"{self.interaction} — {self.manager}"
