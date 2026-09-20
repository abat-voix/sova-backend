from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.workflows.models import ActionOutcome


class ActionOutcomeFilter(SearchFilterMixin):
    """Фильтр исходов действий."""

    action__ids = UUIDInFilter(
        field_name="action",
        label=_("Действия"),
        help_text=_("Фильтр по списку ID действий через запятую"),
    )
    workflow__ids = UUIDInFilter(
        field_name="action__stage__workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую; workflow определяется по действию"),
    )

    class Meta:
        model = ActionOutcome
        fields = (
            "active",
            "comment_required",
            "attachment_required",
        )
        exact_search_fields = ["code"]
