import factory

from sova.core.tests.factories import UserFactory
from sova.messaging.enum import ConversationKind
from sova.messaging.models import Conversation, ConversationParticipant, Message


class ConversationFactory(factory.django.DjangoModelFactory):
    """Фабрика беседы. Для реального сценария используйте сервисы ConversationService."""

    class Meta:
        model = Conversation

    kind = ConversationKind.DIRECT
    dedupe_key = factory.Sequence(lambda n: f"direct:test-{n}")


class ConversationParticipantFactory(factory.django.DjangoModelFactory):
    """Фабрика участия пользователя в беседе."""

    class Meta:
        model = ConversationParticipant

    conversation = factory.SubFactory(ConversationFactory)
    user = factory.SubFactory(UserFactory)


class MessageFactory(factory.django.DjangoModelFactory):
    """Фабрика сообщения."""

    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    sender = factory.SubFactory(UserFactory)
    text = factory.Sequence(lambda n: f"Сообщение {n}")
