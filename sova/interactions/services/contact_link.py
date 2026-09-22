from django.db import IntegrityError, transaction
from django.utils import timezone

from sova.catalog.models import ContactPerson
from sova.interactions.exceptions import ContactLinkError
from sova.interactions.models import Interaction, InteractionContact


def _counterparty(value) -> tuple[str, object] | None:
    """Возвращает тип и ID единственного контрагента объекта."""
    if value.university_id is not None:
        return "university", value.university_id
    if value.b2c_client_id is not None:
        return "b2c_client", value.b2c_client_id
    return None


class ContactLinkService:
    """Единые правила создания и закрытия связей контакта с взаимодействием."""

    @transaction.atomic
    def link(self, interaction: Interaction, contact_person: ContactPerson, actor=None) -> tuple[InteractionContact, bool]:
        locked_interaction = (
            Interaction.objects.select_for_update()
            .select_related("university", "b2c_client")
            .get(pk=interaction.pk)
        )
        try:
            locked_contact = (
                ContactPerson.objects.select_for_update()
                .select_related("university", "b2c_client")
                .get(pk=contact_person.pk)
            )
        except ContactPerson.DoesNotExist as error:
            raise ContactLinkError(
                "contact_not_found",
                "Контактное лицо не найдено.",
                404,
            ) from error

        if not locked_contact.is_active:
            raise ContactLinkError(
                "contact_inactive",
                "Нельзя привязать неактивное контактное лицо.",
                400,
            )
        if _counterparty(locked_interaction) != _counterparty(locked_contact):
            raise ContactLinkError(
                "counterparty_mismatch",
                "Контактное лицо принадлежит другому контрагенту.",
                409,
            )

        existing = InteractionContact.objects.filter(
            interaction=locked_interaction,
            contact_person=locked_contact,
            unlinked_at__isnull=True,
        ).first()
        if existing is not None:
            return existing, False

        try:
            with transaction.atomic():
                link = InteractionContact.objects.create(
                    interaction=locked_interaction,
                    contact_person=locked_contact,
                    linked_by=actor,
                )
        except IntegrityError:
            # The interaction row is locked for all writes through this service;
            # this fallback also handles a caller racing with an older code path.
            existing = InteractionContact.objects.filter(
                interaction=locked_interaction,
                contact_person=locked_contact,
                unlinked_at__isnull=True,
            ).first()
            if existing is None:
                raise
            return existing, False
        return link, True

    @transaction.atomic
    def unlink(self, interaction: Interaction, contact_person: ContactPerson, actor=None) -> InteractionContact:
        locked_interaction = Interaction.objects.select_for_update().get(pk=interaction.pk)
        link = (
            InteractionContact.objects.select_for_update()
            .filter(
                interaction=locked_interaction,
                contact_person_id=contact_person.pk,
                unlinked_at__isnull=True,
            )
            .first()
        )
        if link is None:
            raise ContactLinkError(
                "contact_link_not_found",
                "Активная привязка контактного лица не найдена.",
                404,
            )

        link.unlinked_at = timezone.now()
        link.unlinked_by = actor
        link.save(update_fields=["unlinked_at", "unlinked_by"])
        return link


contact_link_service = ContactLinkService()
