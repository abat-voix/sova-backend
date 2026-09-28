import datetime

import factory

from sova.catalog.tests.factories import ProgramFactory, OrganizationFactory
from sova.interactions.tests.factories import InteractionProgramFactory
from sova.training.enum import QualificationKind
from sova.training.models import (
    Learner,
    LearnerPersonalData,
    TrainingApplication,
    TrainingApplicationLearner,
    TrainingInstructor,
    TrainingInstructorQualification,
    TrainingStream,
)


class TrainingStreamFactory(factory.django.DjangoModelFactory):
    """Фабрика потока обучения."""

    class Meta:
        model = TrainingStream

    interaction_program = factory.SubFactory(InteractionProgramFactory)
    name = factory.Sequence(lambda n: f"Поток {n}")


class TrainingInstructorFactory(factory.django.DjangoModelFactory):
    """Фабрика преподавателя вуза."""

    class Meta:
        model = TrainingInstructor

    last_name = "Петров"
    first_name = "Пётр"
    organization = factory.SubFactory(OrganizationFactory)


class TrainingInstructorQualificationFactory(factory.django.DjangoModelFactory):
    """Фабрика записи о подготовке преподавателя."""

    class Meta:
        model = TrainingInstructorQualification

    instructor = factory.SubFactory(TrainingInstructorFactory)
    kind = QualificationKind.INITIAL
    program = factory.SubFactory(ProgramFactory)
    completed_at = datetime.date(2026, 1, 15)


class LearnerFactory(factory.django.DjangoModelFactory):
    """Фабрика обучающегося."""

    class Meta:
        model = Learner

    last_name = "Иванов"
    first_name = "Михаил"
    email = factory.Sequence(lambda n: f"learner{n}@test.ru")
    phone = factory.Sequence(lambda n: f"7999{n:07d}")


class LearnerPersonalDataFactory(factory.django.DjangoModelFactory):
    """Фабрика персональных данных обучающегося."""

    class Meta:
        model = LearnerPersonalData

    learner = factory.SubFactory(LearnerFactory)


class TrainingApplicationFactory(factory.django.DjangoModelFactory):
    """Фабрика заявки на поток."""

    class Meta:
        model = TrainingApplication

    stream = factory.SubFactory(TrainingStreamFactory)


class TrainingApplicationLearnerFactory(factory.django.DjangoModelFactory):
    """Фабрика участника заявки."""

    class Meta:
        model = TrainingApplicationLearner

    application = factory.SubFactory(TrainingApplicationFactory)
    learner = factory.SubFactory(LearnerFactory)

