from accounts.policy import Action
from sova.core.api.views import SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.api.views.mixins import VisibleInteractionMixin
from sova.processes.models import ActionResult


class ActionResultViewSet(VisibleInteractionMixin, SovaReadOnlyViewSet):
    """
    Результаты действий — журнал: только просмотр.

    Результат пишет движок при завершении действия (`complete`), где проверяются правила исхода:
    принадлежность, активность, обязательные комментарий и вложение. Записи не редактируются и не удаляются.
    """

    serializer_class = serializers.ActionResultSerializer
    interaction_lookup = "action_instance__stage_instance__workflow_instance__interaction"
    queryset = ActionResult.objects.select_related("outcome", "created_by")
    ordering_fields = "__all__"
    search_fields = ("outcome_name_snapshot", "comment")
    filterset_class = filters.ActionResultFilter
    policy_actions = {"list": Action.PROCESSES_READ, "retrieve": Action.PROCESSES_READ}
