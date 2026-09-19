from django.conf import settings
from django.db import models

from sova.crm.models.base import UUIDModel


class License(UUIDModel):
    """
    Лицензия на конкретный ИТ-продукт, выданная в рамках договора.

    Перезаключение не перезаписывает запись, а закрывает её (`is_active=False`,
    `superseded_at`) и создаёт новую — сохраняется история версий (аналогично Responsible).
    """

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )
    signed_at = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата подписания лицензии",
    )
    superseded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Заменена",
    )
    valid_until_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Действует до (год)",
    )
    is_signed = models.BooleanField(
        default=False,
        verbose_name="Подписана",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Действующая",
    )

    contract = models.ForeignKey(
        to="crm.Contract",
        on_delete=models.PROTECT,
        related_name="licenses",
        verbose_name="Договор",
    )
    it_product = models.ForeignKey(
        to="crm.ITProduct",
        on_delete=models.PROTECT,
        related_name="licenses",
        verbose_name="ИТ-продукт",
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="licenses",
        null=True,
        blank=True,
        verbose_name="Создал",
    )

    class Meta:
        verbose_name = "Лицензия"
        verbose_name_plural = "Лицензии"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "it_product"],
                condition=models.Q(is_active=True),
                name="one_active_license_per_contract_product",
            ),
        ]

    def __str__(self):
        return f"{self.contract} — {self.it_product}"
