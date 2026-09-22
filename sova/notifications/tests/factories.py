import factory

from sova.core.tests.factories import UserFactory
from sova.notifications.models import NotificationProfile


class NotificationProfileFactory(factory.django.DjangoModelFactory):
    """Фабрика профиля уведомлений."""

    class Meta:
        model = NotificationProfile

    telegram_chat_id = factory.Sequence(lambda n: f"tg-{n}")
    max_chat_id = factory.Sequence(lambda n: f"max-{n}")
    user = factory.SubFactory(UserFactory)
