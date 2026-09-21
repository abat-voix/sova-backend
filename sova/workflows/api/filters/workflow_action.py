from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.workflows.models import WorkflowAction


class WorkflowActionFilter(SearchFilterMixin):
    """Фильтр действий workflow."""

    stage__ids = UUIDInFilter(
        field_name="stage",
        label=_("Этапы"),
        help_text=_("Фильтр по списку ID этапов через запятую"),
    )
    workflow__ids = UUIDInFilter(
        field_name="stage__workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую; workflow определяется по этапу"),
    )

    class Meta:
        model = WorkflowAction
        fields = (
            "is_optional",
            "is_active",
        )
