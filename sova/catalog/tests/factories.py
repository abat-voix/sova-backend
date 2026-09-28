import factory

from sova.catalog.enum import AddressKind, CatalogType
from sova.catalog.models import (
    OrganizationAddress,
    B2CClient,
    B2CClientContact,
    CatalogImportMapping,
    ContactPerson,
    Direction,
    Product,
    Program,
    Organization,
    OrganizationContact,
    Vendor,
    VendorContact,
)


class VendorFactory(factory.django.DjangoModelFactory):
    """Фабрика вендора."""

    class Meta:
        model = Vendor

    name = factory.Sequence(lambda n: f"Вендор {n}")


class DirectionFactory(factory.django.DjangoModelFactory):
    """Фабрика направления."""

    class Meta:
        model = Direction

    name = factory.Sequence(lambda n: f"Направление {n}")


class ProgramFactory(factory.django.DjangoModelFactory):
    """Фабрика программы."""

    class Meta:
        model = Program

    name = factory.Sequence(lambda n: f"Программа {n}")
    direction = factory.SubFactory(DirectionFactory)


class ProductFactory(factory.django.DjangoModelFactory):
    """Фабрика продукта. Каталожные программы передаются через `programs=[...]`."""

    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Продукт {n}")
    vendor = factory.SubFactory(VendorFactory)

    @factory.post_generation
    def programs(self, create: bool, extracted: list | None, **kwargs) -> None:
        """Привязывает переданные программы."""
        if create and extracted:
            self.programs.set(extracted)


class OrganizationFactory(factory.django.DjangoModelFactory):
    """
    Фабрика организации (по умолчанию — вуз). Местоположение (`country_code`, `region`, `city`, `lat`, `lon`)
    передаётся как отдельные параметры — из него создаётся фактический адрес.
    """

    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Вуз {n}")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        location = {field: kwargs.pop(field) for field in LOCATION_FIELDS if field in kwargs}
        organization = super()._create(model_class, *args, **kwargs)
        if any(value not in ("", None) for value in location.values()):
            OrganizationAddress.objects.create(organization=organization, kind=AddressKind.ACTUAL, **location)
        return organization


LOCATION_FIELDS = ("country_code", "region", "city", "lat", "lon")


class B2CClientFactory(factory.django.DjangoModelFactory):
    """Фабрика B2C-клиента."""

    class Meta:
        model = B2CClient

    full_name = factory.Sequence(lambda n: f"Клиент {n}")


class ContactPersonFactory(factory.django.DjangoModelFactory):
    """Фабрика контактного лица — только человек; связь с организацией — фабрики `*ContactFactory`."""

    class Meta:
        model = ContactPerson

    full_name = factory.Sequence(lambda n: f"Контакт {n}")


class OrganizationContactFactory(factory.django.DjangoModelFactory):
    """Фабрика связи контактного лица с вузом."""

    class Meta:
        model = OrganizationContact

    contact = factory.SubFactory(ContactPersonFactory)
    organization = factory.SubFactory(OrganizationFactory)


class B2CClientContactFactory(factory.django.DjangoModelFactory):
    """Фабрика связи контактного лица с B2C-клиентом."""

    class Meta:
        model = B2CClientContact

    contact = factory.SubFactory(ContactPersonFactory)
    b2c_client = factory.SubFactory(B2CClientFactory)


class VendorContactFactory(factory.django.DjangoModelFactory):
    """Фабрика связи контактного лица с вендором. Продукты передаются через `products=[...]`."""

    class Meta:
        model = VendorContact

    contact = factory.SubFactory(ContactPersonFactory)
    vendor = factory.SubFactory(VendorFactory)

    @factory.post_generation
    def products(self, create: bool, extracted: list | None, **kwargs) -> None:
        """Привязывает переданные продукты."""
        if create and extracted:
            self.products.set(extracted)


class CatalogImportMappingFactory(factory.django.DjangoModelFactory):
    """Фабрика маппинга колонки файла импорта на каноническое поле."""

    class Meta:
        model = CatalogImportMapping

    catalog_type = CatalogType.PRODUCT
    source_column = factory.Sequence(lambda n: f"Колонка {n}")
    # target_field уникален в рамках catalog_type — перебираем допустимые поля продукта.
    target_field = factory.Iterator(["name", "external_code", "vendor", "is_active", "programs"])
