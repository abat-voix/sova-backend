from datetime import timedelta

import factory
from django.utils import timezone

from sova.core.tests.factories import UserFactory
from sova.notifications.models import Notification, NotificationProfile, TelegramLinkToken


class NotificationProfileFactory(factory.django.DjangoModelFactory):
    """Фабрика профиля уведомлений."""

    class Meta:
        model = NotificationProfile

    telegram_chat_id = factory.Sequence(lambda n: f"tg-{n}")
    max_chat_id = factory.Sequence(lambda n: f"max-{n}")
    user = factory.SubFactory(UserFactory)


class NotificationFactory(factory.django.DjangoModelFactory):
    """Фабрика уведомления в системе."""

    class Meta:
        model = Notification

    title = factory.Sequence(lambda n: f"Уведомление {n}")
    text = "Текст уведомления"
    recipient = factory.SubFactory(UserFactory)


class TelegramLinkTokenFactory(factory.django.DjangoModelFactory):
    """Фабрика токена привязки Telegram."""

    class Meta:
        model = TelegramLinkToken

    user = factory.SubFactory(UserFactory)
    expires_at = factory.LazyFunction(lambda: timezone.now() + timedelta(minutes=30))
