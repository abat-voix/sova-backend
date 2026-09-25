import factory

from sova.integrations.enum import IntegrationDirection
from sova.integrations.models import IntegrationMessage


class IntegrationMessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IntegrationMessage

    system = "lms"
    direction = IntegrationDirection.INCOMING
    event_type = "generic.received"
    external_id = factory.Sequence(lambda n: f"event-{n}")
    payload = factory.LazyFunction(lambda: {"custom": {"value": True}})
