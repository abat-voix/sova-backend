from sova.core.api.views import ReadWriteCreateModelMixin, SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.models import StageInstance


class StageInstanceViewSet(ReadWriteCreateModelMixin, SovaReadOnlyViewSet):
    """Экземпляры этапов процесса: просмотр и добавление."""

    read_serializer_class = serializers.StageInstanceSerializer
    serializer_class = serializers.WriteStageInstanceSerializer
    queryset = StageInstance.objects.select_related("stage", "added_by")
    ordering_fields = "__all__"
    search_fields = ("status", "stage__name")
    filterset_class = filters.StageInstanceFilter

    def perform_create(self, serializer: serializers.WriteStageInstanceSerializer) -> None:
        """Привязка текущего пользователя при добавлении этапа."""
        serializer.save(added_by=self.request.user)
