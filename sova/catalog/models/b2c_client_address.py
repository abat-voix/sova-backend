from django.db import models

from sova.catalog.models.address import AbstractAddress
from sova.core.fields import EncryptedTextField


class B2CClientAddress(AbstractAddress):
    """
    Адрес регистрации B2C-клиента (физлица). Страна, регион и город открыты — по ним фильтруют списки; улица, дом,
    квартира и индекс — персональные данные: зашифрованы, полностью их видит только администратор платформы,
    каждый просмотр и изменение пишутся в `B2CClientAddressAccessLog`.
    """

    b2c_client = models.OneToOneField(
        to="catalog.B2CClient",
        on_delete=models.CASCADE,
        related_name="address",
        verbose_name="B2C-клиент",
    )
    street = EncryptedTextField(blank=True, verbose_name="Улица")
    house = EncryptedTextField(blank=True, verbose_name="Дом, корпус, строение")
    apartment = EncryptedTextField(blank=True, verbose_name="Квартира")
    postal_code = EncryptedTextField(blank=True, verbose_name="Индекс")

    class Meta:
        verbose_name = "Адрес B2C-клиента"
        verbose_name_plural = "Адреса B2C-клиентов"

    def __str__(self):
        return f"Адрес: {self.b2c_client}"
