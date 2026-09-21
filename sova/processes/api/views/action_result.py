from sova.core.api.views import SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.models import ActionResult


class ActionResultViewSet(SovaReadOnlyViewSet):
    """
    Результаты действий — журнал: только просмотр.

    Результат пишет движок при завершении действия (`complete`), где проверяются правила исхода:
    принадлежность, активность, обязательные комментарий и вложение. Записи не редактируются и не удаляются.
    """

    serializer_class = serializers.ActionResultSerializer
    queryset = ActionResult.objects.select_related("outcome", "created_by")
    ordering_fields = "__all__"
    search_fields = ("outcome_name_snapshot", "comment")
    filterset_class = filters.ActionResultFilter
