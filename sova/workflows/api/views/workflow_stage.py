from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.models import WorkflowStage


class WorkflowStageViewSet(WorkflowAuditMixin, SovaBaseViewSet):
    """Этапы workflow. Доступны CRUD операции; правки пишутся в аудит."""

    read_serializer_class = serializers.WorkflowStageSerializer
    serializer_class = serializers.WriteWorkflowStageSerializer
    queryset = WorkflowStage.objects.select_related("workflow")
    ordering_fields = "__all__"
    search_fields = ("name", "description")
    filterset_class = filters.WorkflowStageFilter
