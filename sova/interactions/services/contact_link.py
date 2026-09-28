from django.db import IntegrityError, transaction
from django.utils import timezone

from sova.catalog.models import ContactPerson
from sova.catalog.services.contact_affiliation import contact_affiliation_service
from sova.interactions.exceptions import ContactLinkError
from sova.interactions.models import Interaction, InteractionContact, Responsible
from sova.notifications.enum import NotifyType
from sova.notifications.services.event_notification import event_notification_service
from sova.notifications.services.links import interaction_link
from sova.notifications.services.message import Message


class ContactLinkService:
    """
    Единые правила создания и закрытия привязок контакта к взаимодействию.

    Привязать можно только активного человека со связью с контрагентом взаимодействия.
    """

    @transaction.atomic
    def link(self, interaction: Interaction, contact_person: ContactPerson, actor=None) -> tuple[InteractionContact, bool]:
        locked_interaction = (
            Interaction.objects.select_for_update()
            .get(pk=interaction.pk)
        )
        try:
            locked_contact = (
                ContactPerson.objects.select_for_update()
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
        affiliation = contact_affiliation_service.find(
            contact=locked_contact,
            organization=contact_affiliation_service.interaction_counterparty(interaction=locked_interaction),
        )
        if affiliation is None:
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

    @transaction.atomic
    def unlink_from_organization(
        self,
        contact_person: ContactPerson,
        organization_field: str,
        organization_id,
        actor=None,
    ) -> list[InteractionContact]:
        """
        Закрывает привязки человека к активным взаимодействиям организации — он ушёл из неё.

        `organization_field` — FK взаимодействия на контрагента (organization / b2c_client). Неактивные (завершённые)
        взаимодействия не трогаются: их контакты остаются в истории.
        """
        return self._close_links(
            links=InteractionContact.objects.filter(
                contact_person=contact_person,
                **{f"interaction__{organization_field}_id": organization_id},
            ),
            actor=actor,
        )

    @transaction.atomic
    def unlink_everywhere(self, contact_person: ContactPerson, actor=None) -> list[InteractionContact]:
        """Закрывает привязки человека ко всем активным взаимодействиям — он больше не контактное лицо."""
        return self._close_links(links=InteractionContact.objects.filter(contact_person=contact_person), actor=actor)

    def _close_links(self, links, actor=None) -> list[InteractionContact]:
        """
        Закрывает открытые привязки активных взаимодействий из `links`.

        Действующие КАМы каждого затронутого взаимодействия получают уведомление `CONTACT_UNLINKED`: пора назначить
        нового контакта.
        """
        closing = list(
            links.select_for_update(of=("self",))
            .filter(unlinked_at__isnull=True, interaction__is_active=True)
            .select_related("interaction__organization", "interaction__b2c_client")
        )
        now = timezone.now()
        for link in closing:
            link.unlinked_at = now
            link.unlinked_by = actor
            link.save(update_fields=["unlinked_at", "unlinked_by"])
            self._notify_unlinked(link=link, actor=actor)
        return closing

    def _notify_unlinked(self, link: InteractionContact, actor=None) -> None:
        """Уведомляет действующих КАМов взаимодействия; без оставшихся контактов — отдельной строкой."""
        interaction = link.interaction
        counterparty = interaction.organization or interaction.b2c_client
        text = (
            f"Контактное лицо {link.contact_person.full_name} больше не работает в «{counterparty}» "
            "и отвязано от взаимодействия"
        )
        if not InteractionContact.objects.filter(interaction=interaction, unlinked_at__isnull=True).exists():
            text += "\nУ взаимодействия не осталось контактных лиц — назначьте нового"
        message = Message(text=text, link=interaction_link(interaction_id=interaction.pk))
        for responsible in Responsible.objects.filter(
            interaction=interaction, unassigned_at__isnull=True
        ).select_related("manager"):
            event_notification_service.notify(
                notify_type=NotifyType.CONTACT_UNLINKED,
                message=message,
                responsible=responsible.manager,
                actor=actor,
            )


contact_link_service = ContactLinkService()
