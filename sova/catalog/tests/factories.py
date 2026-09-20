import factory

from sova.catalog.enum import ClientKind
from sova.catalog.models import (
    B2CClient,
    ContactPerson,
    ITDirection,
    ITProduct,
    ITProgram,
    University,
    Vendor,
)


class VendorFactory(factory.django.DjangoModelFactory):
    """Фабрика вендора."""

    class Meta:
        model = Vendor

    name = factory.Sequence(lambda n: f"Вендор {n}")


class ITDirectionFactory(factory.django.DjangoModelFactory):
    """Фабрика ИТ-направления."""

    class Meta:
        model = ITDirection

    name = factory.Sequence(lambda n: f"Направление {n}")


class ITProgramFactory(factory.django.DjangoModelFactory):
    """Фабрика ИТ-программы."""

    class Meta:
        model = ITProgram

    name = factory.Sequence(lambda n: f"Программа {n}")
    it_direction = factory.SubFactory(ITDirectionFactory)


class ITProductFactory(factory.django.DjangoModelFactory):
    """Фабрика ИТ-продукта. Каталожные программы передаются через `programs=[...]`."""

    class Meta:
        model = ITProduct

    name = factory.Sequence(lambda n: f"Продукт {n}")
    vendor = factory.SubFactory(VendorFactory)

    @factory.post_generation
    def programs(self, create: bool, extracted: list | None, **kwargs) -> None:
        """Привязывает переданные ИТ-программы."""
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
    """Фабрика контактного лица вуза (по умолчанию) или B2C-клиента."""

    class Meta:
        model = ContactPerson

    full_name = factory.Sequence(lambda n: f"Контакт {n}")
    university = factory.SubFactory(UniversityFactory)
