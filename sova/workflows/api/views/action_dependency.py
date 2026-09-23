from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.models import ActionDependency
from sova.workflows.api.permissions import CanManageWorkflows, WorkflowOwnershipMixin


class ActionDependencyViewSet(WorkflowOwnershipMixin, WorkflowAuditMixin, SovaBaseViewSet):
    """
    Зависимости между действиями. Доступны CRUD операции; правки пишутся в аудит.

    Граф зависимостей должен оставаться ациклическим — циклы отклоняются с 400.
    """

    read_serializer_class = serializers.ActionDependencySerializer
    serializer_class = serializers.WriteActionDependencySerializer
    queryset = ActionDependency.objects.select_related("action", "depends_on_action")
    ordering_fields = "__all__"
    search_fields = ("action__name", "depends_on_action__name")
    filterset_class = filters.ActionDependencyFilter
    permission_classes = (CanManageWorkflows,)
