from django.db import transaction

from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.enum import WorkflowChangeType
from sova.workflows.models import WorkflowAction
from sova.workflows.services import action_outcome_service


class WorkflowActionViewSet(WorkflowAuditMixin, SovaBaseViewSet):
    """
    Действия workflow. Доступны CRUD операции; правки пишутся в аудит.
    Новое действие сразу получает исход «Выполнено» — без исхода его нельзя завершить.
    """

    read_serializer_class = serializers.WorkflowActionSerializer
    serializer_class = serializers.WriteWorkflowActionSerializer
    queryset = WorkflowAction.objects.select_related("stage")
    ordering_fields = "__all__"
    search_fields = ("name", "description")
    filterset_class = filters.WorkflowActionFilter

    @transaction.atomic
    def perform_create(self, serializer) -> None:
        """Сохраняет действие вместе с исходом по умолчанию и пишет обе записи в аудит."""
        super().perform_create(serializer)
        outcome = action_outcome_service.create_default(action=serializer.instance)
        self._record(instance=outcome, change_type=WorkflowChangeType.CREATED)
