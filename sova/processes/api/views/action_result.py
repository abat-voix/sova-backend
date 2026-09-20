from sova.core.api.views import ReadWriteCreateModelMixin, SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.models import ActionResult


class ActionResultViewSet(ReadWriteCreateModelMixin, SovaReadOnlyViewSet):
    """
    Результаты действий — журнал: фиксация и просмотр.

    Записи не редактируются и не удаляются. Исход проверяется по правилам
    действия: принадлежность, активность, обязательные комментарий и вложение.
    """

    read_serializer_class = serializers.ActionResultSerializer
    serializer_class = serializers.WriteActionResultSerializer
    queryset = ActionResult.objects.select_related("outcome", "created_by")
    ordering_fields = "__all__"
    search_fields = ("outcome_name_snapshot", "comment")
    filterset_class = filters.ActionResultFilter

    def perform_create(self, serializer: serializers.WriteActionResultSerializer) -> None:
        """Привязка текущего пользователя при фиксации результата."""
        serializer.save(created_by=self.request.user)
