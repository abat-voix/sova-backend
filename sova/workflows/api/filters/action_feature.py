from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.workflows.models import ActionFeature


class ActionFeatureFilter(SearchFilterMixin):
    """Фильтры настроенных возможностей действий."""

    action__ids = UUIDInFilter(
        field_name="action",
        label=_("Действия"),
        help_text=_("Фильтр по списку ID действий через запятую"),
    )
    workflow__ids = UUIDInFilter(
        field_name="action__stage__workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую"),
    )

    class Meta:
        model = ActionFeature
        fields = ("is_active",)
        exact_search_fields = ["code"]
