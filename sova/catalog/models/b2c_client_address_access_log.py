from django.conf import settings
from django.db import models

from sova.catalog.enum import PersonalDataAccessAction
from sova.core.models import UUIDModel


class B2CClientAddressAccessLog(UUIDModel):
    """Журнал доступа к зашифрованной части адреса B2C-клиента (приказ ФСТЭК № 117)."""

    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        verbose_name="Пользователь",
    )
    b2c_client = models.ForeignKey(
        to="catalog.B2CClient",
        on_delete=models.SET_NULL,
        related_name="address_access_log",
        null=True,
        verbose_name="B2C-клиент",
    )
    accessed_at = models.DateTimeField(auto_now_add=True, verbose_name="Когда")
    fields = models.JSONField(default=list, verbose_name="Поля")
    action = models.CharField(
        max_length=10,
        choices=PersonalDataAccessAction.choices,
        default=PersonalDataAccessAction.READ,
        verbose_name="Действие",
    )
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP-адрес")

    class Meta:
        verbose_name = "Доступ к адресу B2C-клиента"
        verbose_name_plural = "Журнал доступа к адресам B2C-клиентов"
        ordering = ["-accessed_at"]

    def __str__(self):
        return f"{self.user} → {self.b2c_client} ({self.accessed_at:%d.%m.%Y %H:%M})"
