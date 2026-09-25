from sova.core.api.views import SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.api.views.mixins import VisibleInteractionMixin
from sova.processes.models import ActionRollback


class ActionRollbackViewSet(VisibleInteractionMixin, SovaReadOnlyViewSet):
    """Журнал откатов действий: только просмотр. Записи пишет движок при откате действия."""

    serializer_class = serializers.ActionRollbackSerializer
    interaction_lookup = "workflow_instance__interaction"
    queryset = ActionRollback.objects.select_related(
        "from_action_instance__action",
        "to_action_instance__action",
        "created_by",
    )
    ordering_fields = "__all__"
    search_fields = ("reason",)
    filterset_class = filters.ActionRollbackFilter
