from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.models import WorkflowAction


class WorkflowActionViewSet(WorkflowAuditMixin, SovaBaseViewSet):
    """Действия workflow. Доступны CRUD операции; правки пишутся в аудит."""

    read_serializer_class = serializers.WorkflowActionSerializer
    serializer_class = serializers.WriteWorkflowActionSerializer
    queryset = WorkflowAction.objects.select_related("stage")
    ordering_fields = "__all__"
    search_fields = ("name", "description")
    filterset_class = filters.WorkflowActionFilter
