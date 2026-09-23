from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.processes.models import ActionRollback


class ActionRollbackFilter(SearchFilterMixin):
    """Фильтр журнала откатов действий."""

    workflow_instance__ids = UUIDInFilter(
        field_name="workflow_instance",
        label=_("Процессы"),
        help_text=_("Фильтр по списку ID процессов workflow через запятую"),
    )
    stage_instance__ids = UUIDInFilter(
        field_name="stage_instance",
        label=_("Экземпляры этапов"),
        help_text=_("Фильтр по списку ID экземпляров этапов через запятую"),
    )
    created_by__ids = NumberInFilter(
        field_name="created_by",
        label=_("Авторы"),
        help_text=_("Фильтр по списку ID пользователей через запятую"),
    )

    class Meta:
        model = ActionRollback
        fields = ()
