from django.db import models

from sova.catalog.models.contact_affiliation import AbstractContactAffiliation


class OrganizationContact(AbstractContactAffiliation):
    """Связь контактного лица с организацией: должность и способы связи в этой организации."""

    contact = models.ForeignKey(
        to="catalog.ContactPerson",
        on_delete=models.PROTECT,
        related_name="organization_links",
        verbose_name="Контактное лицо",
    )
    organization = models.ForeignKey(
        to="catalog.Organization",
        on_delete=models.CASCADE,
        related_name="contact_links",
        verbose_name="Организация",
    )

    class Meta:
        verbose_name = "Связь с организацией"
        verbose_name_plural = "Связи с организациями"
        ordering = ["contact__full_name"]
        constraints = AbstractContactAffiliation.pair_constraints(organization_field="organization", prefix="organization_contact")

    def __str__(self):
        return f"{self.contact} — {self.organization}"
