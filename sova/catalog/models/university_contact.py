from django.db import models

from sova.catalog.models.contact_affiliation import AbstractContactAffiliation


class UniversityContact(AbstractContactAffiliation):
    """Связь контактного лица с вузом: должность и способы связи в этой организации."""

    contact = models.ForeignKey(
        to="catalog.ContactPerson",
        on_delete=models.PROTECT,
        related_name="university_links",
        verbose_name="Контактное лицо",
    )
    university = models.ForeignKey(
        to="catalog.University",
        on_delete=models.CASCADE,
        related_name="contact_links",
        verbose_name="Вуз",
    )

    class Meta:
        verbose_name = "Связь с вузом"
        verbose_name_plural = "Связи с вузами"
        ordering = ["contact__full_name"]
        constraints = AbstractContactAffiliation.pair_constraints(organization_field="university", prefix="university_contact")

    def __str__(self):
        return f"{self.contact} — {self.university}"
