from sova.core.api.views import SovaReadOnlyViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.models import WorkflowChange
from sova.workflows.api.permissions import CanManageWorkflows


class WorkflowChangeViewSet(SovaReadOnlyViewSet):
    """Журнал изменений структуры workflow — только чтение."""

    read_serializer_class = serializers.WorkflowChangeSerializer
    serializer_class = serializers.WorkflowChangeSerializer
    queryset = WorkflowChange.objects.select_related("created_by")
    ordering_fields = "__all__"
    search_fields = ("change_type", "entity_type")
    filterset_class = filters.WorkflowChangeFilter
    permission_classes = (CanManageWorkflows,)
