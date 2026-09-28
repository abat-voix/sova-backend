import factory

from sova.catalog.tests.factories import (
    DirectionFactory,
    ProductFactory,
    ProgramFactory,
    OrganizationFactory,
)
from sova.core.tests.factories import UserFactory
from sova.interactions.models import (
    Contract,
    Interaction,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    License,
    Responsible,
)


class InteractionFactory(factory.django.DjangoModelFactory):
    """Фабрика взаимодействия с вузом."""

    class Meta:
        model = Interaction

    organization = factory.SubFactory(OrganizationFactory)


class ContractFactory(factory.django.DjangoModelFactory):
    """Фабрика договора."""

    class Meta:
        model = Contract

    contract_number = factory.Sequence(lambda n: f"Д-{n}")
    interaction = factory.SubFactory(InteractionFactory)


class InteractionDirectionFactory(factory.django.DjangoModelFactory):
    """Фабрика направления взаимодействия."""

    class Meta:
        model = InteractionDirection

    interaction = factory.SubFactory(InteractionFactory)
    direction = factory.SubFactory(DirectionFactory)


class InteractionProgramFactory(factory.django.DjangoModelFactory):
    """Фабрика программы взаимодействия."""

    class Meta:
        model = InteractionProgram

    interaction = factory.SubFactory(InteractionFactory)
    program = factory.SubFactory(ProgramFactory)


class InteractionProductFactory(factory.django.DjangoModelFactory):
    """Фабрика продукта взаимодействия (без привязки к программе)."""

    class Meta:
        model = InteractionProduct

    interaction = factory.SubFactory(InteractionFactory)
    product = factory.SubFactory(ProductFactory)


class LicenseFactory(factory.django.DjangoModelFactory):
    """Фабрика лицензии: договор и продукт принадлежат одному взаимодействию."""

    class Meta:
        model = License

    contract = factory.SubFactory(ContractFactory)
    interaction_product = factory.SubFactory(
        InteractionProductFactory,
        interaction=factory.SelfAttribute("..contract.interaction"),
    )


class ResponsibleFactory(factory.django.DjangoModelFactory):
    """Фабрика назначения ответственного (по умолчанию — действующее)."""

    class Meta:
        model = Responsible

    interaction = factory.SubFactory(InteractionFactory)
    manager = factory.SubFactory(UserFactory)
