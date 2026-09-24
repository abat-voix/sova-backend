from collections.abc import Iterable

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from sova.messaging.models import Message
from sova.messaging.realtime import publish_message_created
from sova.messaging.services.conversation import conversation_service


@transaction.atomic
def send_system_message(users: Iterable[AbstractBaseUser], text: str, link: str = "") -> list[Message]:
    """
    Отправляет системное сообщение одному или нескольким пользователям.

    Точка входа для других приложений (workflows, processes, interactions),
    минуя пользовательский API отправки — sender у таких сообщений всегда пуст.
    """
    messages: list[Message] = []
    for user in users:
        conversation = conversation_service.get_or_create_system(user)
        message = Message.objects.create(conversation=conversation, sender=None, text=text, link=link)
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message_at"])
        publish_message_created(message)
        messages.append(message)
    return messages
