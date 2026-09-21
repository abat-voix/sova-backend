from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.models import ActionOutcome


class ActionOutcomeViewSet(WorkflowAuditMixin, SovaBaseViewSet):
    """Исходы действий. Доступны CRUD операции; правки пишутся в аудит."""

    read_serializer_class = serializers.ActionOutcomeSerializer
    serializer_class = serializers.WriteActionOutcomeSerializer
    queryset = ActionOutcome.objects.select_related("action")
    ordering_fields = "__all__"
    search_fields = ("code", "name")
    filterset_class = filters.ActionOutcomeFilter
