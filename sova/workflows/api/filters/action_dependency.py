from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.workflows.models import ActionDependency


class ActionDependencyFilter(SearchFilterMixin):
    """Фильтр зависимостей действий."""

    action__ids = UUIDInFilter(
        field_name="action",
        label=_("Зависимые действия"),
        help_text=_("Фильтр по списку ID действий, имеющих зависимости, через запятую"),
    )
    depends_on_action__ids = UUIDInFilter(
        field_name="depends_on_action",
        label=_("Действия-предусловия"),
        help_text=_("Фильтр по списку ID действий, от которых зависят другие, через запятую"),
    )
    workflow__ids = UUIDInFilter(
        field_name="action__stage__workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую; workflow определяется по действию"),
    )

    class Meta:
        model = ActionDependency
        fields = ("active",)
