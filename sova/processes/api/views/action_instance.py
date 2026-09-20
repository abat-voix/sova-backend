from sova.core.api.views import ReadWriteCreateModelMixin, SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.models import ActionInstance


class ActionInstanceViewSet(ReadWriteCreateModelMixin, SovaReadOnlyViewSet):
    """Экземпляры действий этапа: просмотр и добавление."""

    read_serializer_class = serializers.ActionInstanceSerializer
    serializer_class = serializers.WriteActionInstanceSerializer
    queryset = ActionInstance.objects.select_related("action", "responsible")
    ordering_fields = "__all__"
    search_fields = ("action_name_snapshot", "status")
    filterset_class = filters.ActionInstanceFilter
