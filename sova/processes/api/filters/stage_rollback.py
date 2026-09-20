from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.processes.models import StageRollback


class StageRollbackFilter(SearchFilterMixin):
    """Фильтр журнала откатов."""

    workflow_instance__ids = UUIDInFilter(
        field_name="workflow_instance",
        label=_("Процессы"),
        help_text=_("Фильтр по списку ID процессов workflow через запятую"),
    )
    created_by__ids = NumberInFilter(
        field_name="created_by",
        label=_("Авторы"),
        help_text=_("Фильтр по списку ID пользователей через запятую"),
    )

    class Meta:
        model = StageRollback
        fields = ("mode",)
