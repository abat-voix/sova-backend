from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.permissions import CanManageWorkflows, WorkflowOwnershipMixin
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.models import ActionFeature


class ActionFeatureViewSet(WorkflowOwnershipMixin, WorkflowAuditMixin, SovaBaseViewSet):
    """Возможности действий. CRUD с проверкой владельца и аудитом."""

    read_serializer_class = serializers.ActionFeatureSerializer
    serializer_class = serializers.WriteActionFeatureSerializer
    queryset = ActionFeature.objects.select_related("action")
    ordering_fields = "__all__"
    search_fields = ("code",)
    filterset_class = filters.ActionFeatureFilter
    permission_classes = (CanManageWorkflows,)
