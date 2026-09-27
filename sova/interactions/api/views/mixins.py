from django.db import transaction
from django.db.models import Q, QuerySet

from accounts.policy import Action
from sova.interactions.services import visible_contracts, visible_interactions
from sova.processes.services import workflow_engine_service


class InteractionPartMixin:
    """
    Записи, принадлежащие взаимодействию (состав, история ответственных): видны вместе с ним, а изменять их — значит
    изменять взаимодействие (`interactions.update`).

    Headless-записи импорта реестра (без взаимодействия) видны вместе со своим договором.
    """

    policy_actions = {
        "list": Action.INTERACTIONS_READ,
        "retrieve": Action.INTERACTIONS_READ,
        "create": Action.INTERACTIONS_UPDATE,
        "update": Action.INTERACTIONS_UPDATE,
        "partial_update": Action.INTERACTIONS_UPDATE,
        "destroy": Action.INTERACTIONS_UPDATE,
    }

    def get_queryset(self) -> QuerySet:
        """Записи видимых пользователю взаимодействий и headless-записи видимых договоров."""
        user = self.request.user
        return super().get_queryset().filter(
            Q(interaction__in=visible_interactions(user))
            | Q(interaction__isnull=True, contract__in=visible_contracts(user)),
        )


class SyncProcessesMixin:
    """
    Состав взаимодействия (направления, программы, продукты): после изменения записи досоздаёт
    этапы в идущих процессах взаимодействия, не дожидаясь следующего действия в них.
    """

    def perform_create(self, serializer) -> None:
        with transaction.atomic():
            super().perform_create(serializer)
            workflow_engine_service.sync_interaction(interaction_id=serializer.instance.interaction_id)

    def perform_update(self, serializer) -> None:
        # Запись могли перенести в другое взаимодействие — синхронизируем оба
        previous_interaction_id = serializer.instance.interaction_id
        with transaction.atomic():
            super().perform_update(serializer)
            for interaction_id in {previous_interaction_id, serializer.instance.interaction_id}:
                workflow_engine_service.sync_interaction(interaction_id=interaction_id)

    def perform_destroy(self, instance) -> None:
        interaction_id = instance.interaction_id
        with transaction.atomic():
            super().perform_destroy(instance)
            workflow_engine_service.sync_interaction(interaction_id=interaction_id)
