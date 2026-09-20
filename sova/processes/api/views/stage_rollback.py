from sova.core.api.views import SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.models import StageRollback


class StageRollbackViewSet(SovaReadOnlyViewSet):
    """Журнал откатов этапов: только просмотр. Записи пишет движок при отмене этапа."""

    serializer_class = serializers.StageRollbackSerializer
    queryset = StageRollback.objects.select_related(
        "from_stage_instance__stage",
        "to_stage_instance__stage",
        "created_by",
    )
    ordering_fields = "__all__"
    search_fields = ("reason",)
    filterset_class = filters.StageRollbackFilter
