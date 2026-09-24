from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.models import StageTransition
from sova.workflows.api.permissions import CanManageWorkflows, WorkflowOwnershipMixin


class StageTransitionViewSet(WorkflowOwnershipMixin, WorkflowAuditMixin, SovaBaseViewSet):
    """
    Связи между этапами. Доступны CRUD операции; правки пишутся в аудит.
    Граф связей должен оставаться ациклическим — циклы отклоняются с 400.
    """

    read_serializer_class = serializers.StageTransitionSerializer
    serializer_class = serializers.WriteStageTransitionSerializer
    queryset = StageTransition.objects.select_related("from_stage", "to_stage")
    ordering_fields = "__all__"
    search_fields = ("from_stage__name", "to_stage__name")
    filterset_class = filters.StageTransitionFilter
    permission_classes = (CanManageWorkflows,)
