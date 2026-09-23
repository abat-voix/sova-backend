from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from sova.messaging.enum import ConversationKind
from sova.messaging.models import Conversation, ConversationParticipant


def _direct_dedupe_key(user_a: AbstractBaseUser, user_b: AbstractBaseUser) -> str:
    """Ключ дедупликации личной беседы — не зависит от порядка аргументов."""
    first_id, second_id = sorted((str(user_a.pk), str(user_b.pk)))
    return f"direct:{first_id}:{second_id}"


def _system_dedupe_key(user: AbstractBaseUser) -> str:
    """Ключ дедупликации системной беседы пользователя."""
    return f"system:{user.pk}"


class ConversationService:
    """Создание и поиск бесед. Личная и системная беседа каждой пары/пользователя — в одном экземпляре."""

    @transaction.atomic
    def get_or_create_direct(self, user_a: AbstractBaseUser, user_b: AbstractBaseUser) -> Conversation:
        """Возвращает личную беседу двух пользователей, создавая её при первом обращении."""
        if user_a.pk == user_b.pk:
            raise ValueError("Личная беседа требует двух разных пользователей.")

        conversation, created = Conversation.objects.get_or_create(
            dedupe_key=_direct_dedupe_key(user_a, user_b),
            defaults={"kind": ConversationKind.DIRECT},
        )
        if created:
            ConversationParticipant.objects.bulk_create(
                [
                    ConversationParticipant(conversation=conversation, user=user_a),
                    ConversationParticipant(conversation=conversation, user=user_b),
                ]
            )
        return conversation

    @transaction.atomic
    def get_or_create_system(self, user: AbstractBaseUser) -> Conversation:
        """Возвращает системную беседу пользователя, создавая её при первом обращении."""
        conversation, created = Conversation.objects.get_or_create(
            dedupe_key=_system_dedupe_key(user),
            defaults={"kind": ConversationKind.SYSTEM},
        )
        if created:
            ConversationParticipant.objects.create(conversation=conversation, user=user)
        return conversation


conversation_service = ConversationService()
