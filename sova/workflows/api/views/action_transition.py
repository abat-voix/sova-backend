from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.models import ActionTransition
from sova.workflows.api.permissions import CanManageWorkflows, WorkflowOwnershipMixin


class ActionTransitionViewSet(WorkflowOwnershipMixin, WorkflowAuditMixin, SovaBaseViewSet):
    """Переходы между действиями. Доступны CRUD операции; правки пишутся в аудит."""

    read_serializer_class = serializers.ActionTransitionSerializer
    serializer_class = serializers.WriteActionTransitionSerializer
    queryset = ActionTransition.objects.select_related("outcome", "target_action")
    ordering_fields = "__all__"
    search_fields = ("outcome__name", "outcome__code", "target_action__name")
    filterset_class = filters.ActionTransitionFilter
    permission_classes = (CanManageWorkflows,)
