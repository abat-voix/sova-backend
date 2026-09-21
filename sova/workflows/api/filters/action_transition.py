from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.workflows.models import ActionTransition


class ActionTransitionFilter(SearchFilterMixin):
    """Фильтр переходов действий."""

    outcome__ids = UUIDInFilter(
        field_name="outcome",
        label=_("Исходы"),
        help_text=_("Фильтр по списку ID исходов через запятую"),
    )
    action__ids = UUIDInFilter(
        field_name="outcome__action",
        label=_("Исходное действие"),
        help_text=_("Переходы, запускаемые исходами указанных действий, ID через запятую"),
    )
    target_action__ids = UUIDInFilter(
        field_name="target_action",
        label=_("Целевые действия"),
        help_text=_("Фильтр по списку ID целевых действий через запятую"),
    )
    workflow__ids = UUIDInFilter(
        field_name="outcome__action__stage__workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую; workflow определяется по исходу"),
    )

    class Meta:
        model = ActionTransition
        fields = ("is_active",)
