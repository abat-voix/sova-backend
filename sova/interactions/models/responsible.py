from django.conf import settings
from django.db import models

from sova.core.models import UUIDModel


class Responsible(UUIDModel):
    """
    Назначение ответственного менеджера (КАМ) на взаимодействие, с историей.

    Привязана к Interaction (взаимодействию), а не к Organization/B2CClient целиком — у каждого взаимодействия
    своя история ответственных, параллельные взаимодействия одного контрагента могут вести
    разных людей. Действующих КАМов у взаимодействия может быть несколько, но один менеджер
    не может быть назначен на одно взаимодействие дважды одновременно.

    Импорт реестра договоров назначает КАМов headless-договору (`contract`, без `interaction`). При создании
    взаимодействия из договора назначения переходят на взаимодействие, `contract` остаётся — видно, что
    назначение пришло из реестра.
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
        null=True,
        blank=True,
        verbose_name="Взаимодействие",
    )
    contract = models.ForeignKey(
        to="interactions.Contract",
        on_delete=models.CASCADE,
        related_name="responsibles",
        null=True,
        blank=True,
        verbose_name="Договор",
        help_text="Заполнен, если назначение пришло из реестра договоров; остаётся и после перехода на взаимодействие.",
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
            models.CheckConstraint(
                condition=models.Q(interaction__isnull=False) | models.Q(contract__isnull=False),
                name="responsible_has_owner",
            ),
            models.UniqueConstraint(
                fields=["interaction", "manager"],
                condition=models.Q(unassigned_at__isnull=True),
                name="one_active_responsible_per_manager",
            ),
            models.UniqueConstraint(
                fields=["contract", "manager"],
                condition=models.Q(unassigned_at__isnull=True),
                name="one_active_responsible_per_contract",
            ),
        ]

    def __str__(self):
        return f"{self.interaction or self.contract} — {self.manager}"
