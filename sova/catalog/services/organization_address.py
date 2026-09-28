from django.db import transaction
from django.db.models import DecimalField, OuterRef, QuerySet, Subquery
from django.db.models.functions import Coalesce

from sova.catalog.enum import AddressKind
from sova.catalog.models import Organization, OrganizationAddress

# Части адреса организации, которые принимает сохранение
ADDRESS_FIELDS = (
    "country_code", "region", "city", "street", "house", "office", "postal_code", "lat", "lon",
)


class OrganizationAddressService:
    """
    Адреса организации: юридический и фактический. Фактический совпадает с юридическим, если стоит
    `Organization.actual_same_as_legal`, — тогда он не хранится, а берётся юридический. Точка на карте — по
    фактическому адресу; если у него нет координат, — по юридическому.
    """

    @staticmethod
    def _stored(organization: Organization, kind: str) -> OrganizationAddress | None:
        """Сохранённый адрес типа `kind`; берёт из prefetch `addresses`, если он есть."""
        prefetched = getattr(organization, "_prefetched_objects_cache", {}).get("addresses")
        if prefetched is not None:
            return next((address for address in prefetched if address.kind == kind), None)
        return organization.addresses.filter(kind=kind).first()

    def legal(self, organization: Organization) -> OrganizationAddress | None:
        """Юридический адрес."""
        return self._stored(organization, AddressKind.LEGAL)

    def actual(self, organization: Organization) -> OrganizationAddress | None:
        """Фактический адрес с учётом отметки «совпадает с юридическим»."""
        if organization.actual_same_as_legal:
            return self.legal(organization)
        return self._stored(organization, AddressKind.ACTUAL)

    def city(self, organization: Organization) -> str:
        """Город организации — по фактическому адресу, иначе по юридическому."""
        address = self.actual(organization) or self.legal(organization)
        return address.city if address else ""

    @transaction.atomic
    def save(self, organization: Organization, changes: dict) -> None:
        """
        Применяет изменения адресов. `changes` содержит только переданные ключи: `legal_address` и
        `actual_address` — словарь частей адреса (сохранить) или `None` (удалить), `actual_same_as_legal` — отметку.
        Если отметка стоит, отдельный фактический адрес удаляется.
        """
        if "actual_same_as_legal" in changes:
            organization.actual_same_as_legal = changes["actual_same_as_legal"]
            organization.save(update_fields=["actual_same_as_legal", "updated_at"])
        if "legal_address" in changes:
            self._apply(organization, AddressKind.LEGAL, changes["legal_address"])
        if organization.actual_same_as_legal:
            organization.addresses.filter(kind=AddressKind.ACTUAL).delete()
        elif "actual_address" in changes:
            self._apply(organization, AddressKind.ACTUAL, changes["actual_address"])
        if hasattr(organization, "_prefetched_objects_cache"):
            organization._prefetched_objects_cache.pop("addresses", None)

    @staticmethod
    def _apply(organization: Organization, kind: str, values: dict | None) -> None:
        if values is None:
            organization.addresses.filter(kind=kind).delete()
            return
        address = organization.addresses.filter(kind=kind).first() or OrganizationAddress(
            organization=organization, kind=kind
        )
        for field in ADDRESS_FIELDS:
            if field in values:
                setattr(address, field, values[field])
        address.full_clean()
        address.save()

    @transaction.atomic
    def update_location(self, organization: Organization, values: dict) -> None:
        """
        Обновляет местоположение из справочника (страна, регион, город, координаты) в фактическом адресе, не трогая
        улицу и дом. Если фактический адрес совпадает с юридическим, обновляется юридический.
        """
        kind = AddressKind.LEGAL if organization.actual_same_as_legal else AddressKind.ACTUAL
        address = organization.addresses.filter(kind=kind).first()
        if address is None and not any(value not in ("", None) for value in values.values()):
            return
        self._apply(organization, kind, values)

    @staticmethod
    def with_coordinates(queryset: QuerySet[Organization]) -> QuerySet[Organization]:
        """Аннотирует `lat`/`lon` точки на карте: фактический адрес, если у него есть координаты, иначе юридический."""

        def coordinate(field: str, kind: str):
            return Subquery(
                OrganizationAddress.objects
                .filter(organization=OuterRef("pk"), kind=kind, lat__isnull=False)
                .values(field)[:1]
            )

        output = DecimalField(max_digits=9, decimal_places=6)
        return queryset.annotate(
            lat=Coalesce(coordinate("lat", AddressKind.ACTUAL), coordinate("lat", AddressKind.LEGAL), output_field=output),
            lon=Coalesce(coordinate("lon", AddressKind.ACTUAL), coordinate("lon", AddressKind.LEGAL), output_field=output),
        )


organization_address_service = OrganizationAddressService()
