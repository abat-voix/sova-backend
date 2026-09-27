import factory

from sova.catalog.enum import CatalogType, ClientKind
from sova.catalog.models import (
    B2CClient,
    B2CClientContact,
    CatalogImportMapping,
    ContactPerson,
    Direction,
    Product,
    Program,
    University,
    UniversityContact,
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


class UniversityFactory(factory.django.DjangoModelFactory):
    """Фабрика вуза."""

    class Meta:
        model = University

    name = factory.Sequence(lambda n: f"Вуз {n}")


class B2CClientFactory(factory.django.DjangoModelFactory):
    """Фабрика B2C-клиента."""

    class Meta:
        model = B2CClient

    full_name = factory.Sequence(lambda n: f"Клиент {n}")
    kind = ClientKind.INDIVIDUAL


class ContactPersonFactory(factory.django.DjangoModelFactory):
    """Фабрика контактного лица — только человек; связь с организацией — фабрики `*ContactFactory`."""

    class Meta:
        model = ContactPerson

    full_name = factory.Sequence(lambda n: f"Контакт {n}")


class UniversityContactFactory(factory.django.DjangoModelFactory):
    """Фабрика связи контактного лица с вузом."""

    class Meta:
        model = UniversityContact

    contact = factory.SubFactory(ContactPersonFactory)
    university = factory.SubFactory(UniversityFactory)


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
