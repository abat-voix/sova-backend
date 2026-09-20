from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.workflows.models import WorkflowStage


class WorkflowStageFilter(SearchFilterMixin):
    """Фильтр этапов workflow."""

    workflow__ids = UUIDInFilter(
        field_name="workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую"),
    )

    class Meta:
        model = WorkflowStage
        fields = (
            "type",
            "is_initial",
            "is_final",
            "is_optional",
            "active",
        )
