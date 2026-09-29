from django.db import models

from sova.catalog.models.contact_affiliation import AbstractContactAffiliation


class VendorContact(AbstractContactAffiliation):
    """
    Связь контактного лица с вендором: должность, способы связи и продукты вендора, за которые он отвечает.

    `products` — только продукты этого вендора; проверяет сервис связей и admin.
    """

    contact = models.ForeignKey(
        to="catalog.ContactPerson",
        on_delete=models.PROTECT,
        related_name="vendor_links",
        verbose_name="Контактное лицо",
    )
    vendor = models.ForeignKey(
        to="catalog.Vendor",
        on_delete=models.CASCADE,
        related_name="contact_links",
        verbose_name="Вендор",
    )
    products = models.ManyToManyField(
        to="catalog.Product",
        related_name="vendor_contacts",
        blank=True,
        verbose_name="Продукты",
    )

    class Meta:
        verbose_name = "Связь с вендором"
        verbose_name_plural = "Связи с вендорами"
        ordering = ["contact__full_name"]
        constraints = AbstractContactAffiliation.pair_constraints(organization_field="vendor", prefix="vendor_contact")

    def __str__(self):
        return f"{self.contact} — {self.vendor}"
