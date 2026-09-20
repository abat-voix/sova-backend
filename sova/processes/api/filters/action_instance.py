from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.processes.models import ActionInstance


class ActionInstanceFilter(SearchFilterMixin):
    """Фильтр экземпляров действий."""

    stage_instance__ids = UUIDInFilter(
        field_name="stage_instance",
        label=_("Экземпляры этапов"),
        help_text=_("Фильтр по списку ID экземпляров этапов через запятую"),
    )
    workflow_instance__ids = UUIDInFilter(
        field_name="stage_instance__workflow_instance",
        label=_("Процессы"),
        help_text=_("Фильтр по списку ID процессов workflow через запятую; определяется по этапу"),
    )
    action__ids = UUIDInFilter(
        field_name="action",
        label=_("Действия"),
        help_text=_("Фильтр по списку ID действий workflow через запятую"),
    )
    responsible__ids = NumberInFilter(
        field_name="responsible",
        label=_("Ответственные"),
        help_text=_("Фильтр по списку ID пользователей-исполнителей через запятую"),
    )

    class Meta:
        model = ActionInstance
        fields = ("status",)
