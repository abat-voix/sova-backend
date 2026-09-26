from collections.abc import Iterable

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from accounts.models import SystemRole
from accounts.services import get_system_role
from sova.interactions.models import Interaction
from sova.messaging.enum import ConversationKind
from sova.messaging.models import Conversation, ConversationParticipant
from sova.messaging.realtime import publish_conversation_created, publish_participants_added


def _direct_dedupe_key(user_a: AbstractBaseUser, user_b: AbstractBaseUser) -> str:
    """Ключ дедупликации личной беседы — не зависит от порядка аргументов."""
    first_id, second_id = sorted((str(user_a.pk), str(user_b.pk)))
    return f"direct:{first_id}:{second_id}"


def _system_dedupe_key(user: AbstractBaseUser) -> str:
    """Ключ дедупликации системной беседы пользователя."""
    return f"system:{user.pk}"


def _interaction_dedupe_key(interaction: Interaction) -> str:
    """Ключ дедупликации чата Взаимодействия."""
    return f"interaction:{interaction.pk}"


class ConversationService:
    """Создание и поиск бесед. Личная, системная беседа и чат Взаимодействия — в одном экземпляре."""

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
            publish_conversation_created(conversation)
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
            publish_conversation_created(conversation)
        return conversation

    @transaction.atomic
    def get_or_create_interaction(
        self,
        interaction: Interaction,
        actor: AbstractBaseUser,
        users: Iterable[AbstractBaseUser] = (),
    ) -> tuple[Conversation, bool]:
        """
        Возвращает чат Взаимодействия, создавая его при первом обращении.

        Участниками при создании становятся автор и переданные пользователи.
        Повторное обращение не меняет состав уже существующего чата — для этого
        есть add_participants. Уникальность dedupe_key и OneToOneField на
        Взаимодействие защищают от дублей при параллельных запросах: проигравшая
        транзакция получит IntegrityError, перехваченный get_or_create(), и
        вернёт уже созданную беседу без повторного добавления участников.
        """
        participant_users = list(users)
        participant_ids = [user.pk for user in participant_users]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("Идентификаторы участников не должны повторяться.")
        if any(not user.is_active for user in participant_users):
            raise ValueError("Участником чата может быть только активный пользователь.")

        conversation, created = Conversation.objects.get_or_create(
            dedupe_key=_interaction_dedupe_key(interaction),
            defaults={
                "kind": ConversationKind.INTERACTION,
                "interaction": interaction,
                "created_by": actor,
            },
        )
        if created:
            participants = {actor.pk: actor}
            participants.update({user.pk: user for user in participant_users})
            ConversationParticipant.objects.bulk_create(
                ConversationParticipant(conversation=conversation, user=user) for user in participants.values()
            )
            publish_conversation_created(conversation)
        return conversation, created

    @transaction.atomic
    def add_participants(
        self,
        conversation: Conversation,
        users: Iterable[AbstractBaseUser],
    ) -> list[AbstractBaseUser]:
        """
        Добавляет в чат пользователей, которые ещё не его участники.

        Приглашение открывает доступ к уже накопленной истории чата, но не
        меняет права на само Взаимодействие. Идемпотентно: уже состоящие в
        чате пользователи из users пропускаются молча.
        """
        participant_users = list(users)
        existing_ids = set(
            ConversationParticipant.objects.filter(conversation=conversation).values_list("user_id", flat=True)
        )
        new_users = [user for user in participant_users if user.pk not in existing_ids]
        if new_users:
            ConversationParticipant.objects.bulk_create(
                ConversationParticipant(conversation=conversation, user=user) for user in new_users
            )
            new_user_ids = [user.pk for user in new_users]
            publish_conversation_created(conversation, recipient_ids=new_user_ids)
            publish_participants_added(conversation, new_user_ids)
        return new_users

    def can_add_participants(self, conversation: Conversation, actor: AbstractBaseUser) -> bool:
        """Создатель чата, руководитель или администратор платформы могут менять состав."""
        if conversation.created_by_id == actor.pk:
            return True
        return get_system_role(actor) in (SystemRole.HEAD, SystemRole.PLATFORM_ADMIN)


conversation_service = ConversationService()
