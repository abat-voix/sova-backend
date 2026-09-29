from collections.abc import Iterable

from django.db import transaction
from django.db.models import OuterRef, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce

from sova.catalog.enum import ContactChannel
from sova.catalog.models import (
    B2CClient,
    B2CClientContact,
    ContactPerson,
    Product,
    Organization,
    OrganizationContact,
    Vendor,
    VendorContact,
)
from sova.catalog.models.contact_affiliation import AbstractContactAffiliation

ContactOwner = Organization | B2CClient | Vendor
Affiliation = OrganizationContact | B2CClientContact | VendorContact

# Тип организации → (модель связи, FK связи на организацию, related_name связей у ContactPerson).
_ADAPTERS: dict[type, tuple[type[AbstractContactAffiliation], str, str]] = {
    Organization: (OrganizationContact, "organization", "organization_links"),
    B2CClient: (B2CClientContact, "b2c_client", "b2c_client_links"),
    Vendor: (VendorContact, "vendor", "vendor_links"),
}


class ContactAffiliationService:
    """
    Связи человека с организациями — единственное место, которое знает, какая модель связи у какой организации.

    Вызывающий код передаёт саму организацию (`Organization` / `B2CClient` / `Vendor`) и не разбирает типы.
    Новый тип организации — новая модель связи и строка в `_ADAPTERS`, без изменений у вызывающих.
    """

    def type_code(self, organization: ContactOwner) -> str:
        """Код типа организации в API: organization, b2c_client, vendor."""
        return self._adapter(organization=organization)[1]

    def model_for(self, organization: ContactOwner) -> type[AbstractContactAffiliation]:
        """Модель связи для организации."""
        return self._adapter(organization=organization)[0]

    def organization_of(self, affiliation: Affiliation) -> ContactOwner:
        """Организация, с которой связан человек."""
        return getattr(affiliation, self._field_of(affiliation=affiliation))

    def links_of(self, contact: ContactPerson) -> list[Affiliation]:
        """
        Все связи человека с организациями: от новых к старым.

        Для чтения; предзагрузка — через `prefetch_links`.
        """
        links = [
            link
            for _model, _field, related_name in _ADAPTERS.values()
            for link in getattr(contact, related_name).all()
        ]
        return sorted(links, key=lambda link: -link.created_at.timestamp())

    def prefetch_links(self, queryset: QuerySet[ContactPerson]) -> QuerySet[ContactPerson]:
        """Предзагружает связи всех типов с организациями — список контактов без N+1."""
        lookups = [f"{related_name}__{field}" for _model, field, related_name in _ADAPTERS.values()]
        return queryset.prefetch_related(*lookups, "vendor_links__products")

    def find(self, contact: ContactPerson, organization: ContactOwner) -> Affiliation | None:
        """Связь человека с организацией; не связан — None."""
        model, field, _related_name = self._adapter(organization=organization)
        return model.objects.filter(contact=contact, **{field: organization}).first()

    def get_or_create(self, contact: ContactPerson, organization: ContactOwner) -> tuple[Affiliation, bool]:
        """Связь человека с организацией; True — создана."""
        model, field, _related_name = self._adapter(organization=organization)
        return model.objects.get_or_create(contact=contact, **{field: organization})

    @transaction.atomic
    def create_contact(
        self,
        organization: ContactOwner,
        full_name: str,
        email: str = "",
        phone: str = "",
        telegram: str = "",
        position: str = "",
        preferred_channels: Iterable[str] = (),
    ) -> Affiliation:
        """Создаёт человека сразу со связью с организацией."""
        contact = ContactPerson.objects.create(full_name=full_name, email=email, phone=phone, telegram=telegram)
        model, field, _related_name = self._adapter(organization=organization)
        return model.objects.create(
            contact=contact,
            position=position,
            preferred_channels=list(preferred_channels),
            **{field: organization},
        )

    def unfilled_channels(
        self,
        channels: Iterable[str],
        email: str = "",
        phone: str = "",
        telegram: str = "",
    ) -> list[str]:
        """Способы связи, для которых у человека не заполнено поле: «Телефон» требует телефон, «Почта» — email и т. д."""
        values = {ContactChannel.EMAIL: email, ContactChannel.PHONE: phone, ContactChannel.TELEGRAM: telegram}
        return [channel for channel in channels if not (values.get(channel) or "").strip()]

    def used_channels(self, contact: ContactPerson) -> set[str]:
        """Способы связи, выбранные хотя бы в одной связи человека."""
        return {channel for link in self.links_of(contact=contact) for channel in link.preferred_channels}

    def set_products(self, affiliation: VendorContact, products: Iterable[Product]) -> None:
        """Продукты, за которые отвечает контакт вендора; только продукты этого вендора."""
        products = list(products)
        foreign = [product.name for product in products if product.vendor_id != affiliation.vendor_id]
        if foreign:
            raise ValueError(f"продукты не принадлежат вендору {affiliation.vendor}: {', '.join(foreign)}")
        affiliation.products.set(products)

    @transaction.atomic
    def delete(self, affiliation: Affiliation, actor=None) -> list:
        """
        Человек ушёл из организации: связь удаляется вместе с должностью, способами связи и продуктами.

        Для организации и B2C-клиента его привязки к активным взаимодействиям организации закрываются, действующие КАМы
        получают уведомление. Возвращает закрытые привязки `InteractionContact`. Вендор не бывает контрагентом
        взаимодействия — связь с ним просто удаляется.
        """
        from sova.interactions.services.contact_link import contact_link_service

        field = self._field_of(affiliation=affiliation)
        closed = []
        if field != "vendor":
            closed = contact_link_service.unlink_from_organization(
                contact_person=affiliation.contact,
                organization_field=field,
                organization_id=getattr(affiliation, f"{field}_id"),
                actor=actor,
            )
        affiliation.delete()
        return closed

    def activate_contact(self, contact: ContactPerson) -> None:
        """У человека снова есть организация, где он работает: выключенный человек включается."""
        if not contact.is_active:
            contact.is_active = True
            contact.save(update_fields=["is_active", "updated_at"])

    @transaction.atomic
    def deactivate_contact(self, contact: ContactPerson, actor=None) -> list:
        """
        Человек ушёл отовсюду: он выключается, его привязки ко всем активным взаимодействиям закрываются (КАМы
        уведомлены), все его связи удаляются.

        Связи удаляются, чтобы при включении человека не ожили устаревшие: вернувшемуся связи создают заново там, где
        он работает (это и включает его — `activate_contact`). Возвращает закрытые привязки.
        """
        from sova.interactions.services.contact_link import contact_link_service

        if contact.is_active:
            contact.is_active = False
            contact.save(update_fields=["is_active", "updated_at"])
        closed = contact_link_service.unlink_everywhere(contact_person=contact, actor=actor)
        for model, _field, _related_name in _ADAPTERS.values():
            model.objects.filter(contact=contact).delete()
        # Предзагруженные связи устарели: по этому же объекту строится ответ API и admin.
        contact.refresh_from_db()
        return closed

    @transaction.atomic
    def delete_contact(self, contact: ContactPerson) -> None:
        """
        Удаляет человека вместе со связями.

        Человек хоть раз был привязан к взаимодействию — `ProtectedError` (409 `protected`): история привязок защищает
        его от удаления, такого выключают.
        """
        for _model, _field, related_name in _ADAPTERS.values():
            getattr(contact, related_name).all().delete()
        contact.delete()

    def contacts_for(self, organization: ContactOwner) -> QuerySet[ContactPerson]:
        """Люди, связанные с организацией."""
        _model, field, related_name = self._adapter(organization=organization)
        return ContactPerson.objects.filter(**{f"{related_name}__{field}": organization}).distinct()

    def position_for(self, contact: ContactPerson, organization: ContactOwner | None) -> str:
        """Должность человека в организации; не связан — пустая строка."""
        if organization is None:
            return ""
        affiliation = self.find(contact=contact, organization=organization)
        return affiliation.position if affiliation is not None else ""

    def interaction_counterparty(self, interaction) -> Organization | B2CClient:
        """Контрагент взаимодействия — организация или B2C-клиент."""
        return interaction.organization or interaction.b2c_client

    def annotate_interaction_position(self, queryset: QuerySet) -> QuerySet:
        """
        Добавляет привязкам `InteractionContact` поле `position` — должность у контрагента взаимодействия.

        Одна подзапросом на тип контрагента вместо запроса на каждую привязку.
        """
        positions = [
            Subquery(
                model.objects.filter(
                    contact=OuterRef("contact_person"),
                    **{field: OuterRef(f"interaction__{field}")},
                ).values("position")[:1]
            )
            for model, field, _related_name in _ADAPTERS.values()
            if field != "vendor"
        ]
        return queryset.annotate(position=Coalesce(*positions, Value("")))

    def _adapter(self, organization: ContactOwner) -> tuple[type[AbstractContactAffiliation], str, str]:
        """Модель связи, FK на организацию и related_name у ContactPerson для типа организации."""
        try:
            return _ADAPTERS[type(organization)]
        except KeyError:
            raise ValueError(f"У организации типа {type(organization).__name__} нет контактных лиц.") from None

    def _field_of(self, affiliation: Affiliation) -> str:
        """FK связи на организацию."""
        for model, field, _related_name in _ADAPTERS.values():
            if isinstance(affiliation, model):
                return field
        raise ValueError(f"Неизвестная связь {type(affiliation).__name__}.")


contact_affiliation_service = ContactAffiliationService()
