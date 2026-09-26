from django.db import transaction

from sova.processes.services import workflow_engine_service


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
