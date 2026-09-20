from django.db import transaction
from django.db.models import Model

from sova.workflows.enum import WorkflowChangeType
from sova.workflows.services import workflow_audit_service


class WorkflowAuditMixin:
    """
    Журналирование правок структуры workflow в WorkflowChange.

    Сохранение и запись аудита выполняются в одной транзакции: изменение без
    записи в аудит (и наоборот) не остаётся. Подключается к ViewSet'ам
    сущностей структуры перед `SovaBaseViewSet`.
    """

    @transaction.atomic
    def perform_create(self, serializer) -> None:
        """Сохраняет новый объект и пишет запись created."""
        super().perform_create(serializer)
        self._record(instance=serializer.instance, change_type=WorkflowChangeType.CREATED)

    @transaction.atomic
    def perform_update(self, serializer) -> None:
        """Сохраняет изменения и пишет запись updated."""
        super().perform_update(serializer)
        self._record(instance=serializer.instance, change_type=WorkflowChangeType.UPDATED)

    @transaction.atomic
    def perform_destroy(self, instance: Model) -> None:
        """Пишет запись deleted до удаления — пока читается цепочка связей."""
        self._record(instance=instance, change_type=WorkflowChangeType.DELETED)
        super().perform_destroy(instance)

    def _record(self, instance: Model, change_type: WorkflowChangeType) -> None:
        """Записывает изменение от имени текущего пользователя."""
        workflow_audit_service.record(
            instance=instance,
            change_type=change_type,
            changed_by=self.request.user,
        )
