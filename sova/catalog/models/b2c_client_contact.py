from django.db import models

from sova.catalog.models.contact_affiliation import AbstractContactAffiliation


class B2CClientContact(AbstractContactAffiliation):
    """Связь контактного лица с B2C-клиентом: должность и способы связи в этой организации."""

    contact = models.ForeignKey(
        to="catalog.ContactPerson",
        on_delete=models.PROTECT,
        related_name="b2c_client_links",
        verbose_name="Контактное лицо",
    )
    b2c_client = models.ForeignKey(
        to="catalog.B2CClient",
        on_delete=models.CASCADE,
        related_name="contact_links",
        verbose_name="B2C-клиент",
    )

    class Meta:
        verbose_name = "Связь с B2C-клиентом"
        verbose_name_plural = "Связи с B2C-клиентами"
        ordering = ["contact__full_name"]
        constraints = AbstractContactAffiliation.pair_constraints(organization_field="b2c_client", prefix="b2c_client_contact")

    def __str__(self):
        return f"{self.contact} — {self.b2c_client}"
