from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.workflows.models import StageTransition


class StageTransitionFilter(SearchFilterMixin):
    """Фильтр связей между этапами."""

    from_stage__ids = UUIDInFilter(
        field_name="from_stage",
        label=_("Этапы-источники"),
        help_text=_("Фильтр по списку ID этапов, после которых открываются другие, через запятую"),
    )
    to_stage__ids = UUIDInFilter(
        field_name="to_stage",
        label=_("Этапы-цели"),
        help_text=_("Фильтр по списку ID этапов, которые открываются после других, через запятую"),
    )
    workflow__ids = UUIDInFilter(
        field_name="from_stage__workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую; workflow определяется по этапу-источнику"),
    )

    class Meta:
        model = StageTransition
        fields = ("is_active",)
