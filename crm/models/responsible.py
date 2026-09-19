from django.conf import settings
from django.db import models

from crm.models.base import UUIDModel


class Responsible(UUIDModel):
    """
    Назначение ответственного менеджера (КАМ) на сделку, с историей.

    Привязана к Contact (сделке), а не к University/B2CClient целиком — у каждой сделки
    своя история ответственных, параллельные сделки одного контрагента могут вести
    разных людей.
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

    contact = models.ForeignKey(
        to="crm.Contact",
        on_delete=models.CASCADE,
        related_name="responsibles",
        verbose_name="Сделка",
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
                fields=["contact"],
                condition=models.Q(unassigned_at__isnull=True),
                name="one_active_responsible_per_contact",
            ),
        ]

    def __str__(self):
        return f"{self.contact} — {self.manager}"
