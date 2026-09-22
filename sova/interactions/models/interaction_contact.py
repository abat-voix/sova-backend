from django.conf import settings
from django.db import models
from django.db.models import Q

from sova.core.models import UUIDModel


class InteractionContact(UUIDModel):
    """История привязок контактных лиц к взаимодействию."""

    interaction = models.ForeignKey(
        "interactions.Interaction",
        on_delete=models.CASCADE,
        related_name="contact_links",
        verbose_name="Взаимодействие",
    )
    contact_person = models.ForeignKey(
        "catalog.ContactPerson",
        on_delete=models.PROTECT,
        related_name="interaction_links",
        verbose_name="Контактное лицо",
    )
    linked_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата привязки",
    )
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interaction_contact_links",
        verbose_name="Кем привязан",
    )
    unlinked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата отвязки",
    )
    unlinked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interaction_contact_unlinks",
        verbose_name="Кем отвязан",
    )

    class Meta:
        verbose_name = "Контакт взаимодействия"
        verbose_name_plural = "Контакты взаимодействий"
        ordering = ["linked_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["interaction", "contact_person"],
                condition=Q(unlinked_at__isnull=True),
                name="unique_active_interaction_contact",
            ),
        ]
        indexes = [
            models.Index(
                fields=["interaction", "unlinked_at"],
                name="interaction_contact_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.interaction} — {self.contact_person}"
