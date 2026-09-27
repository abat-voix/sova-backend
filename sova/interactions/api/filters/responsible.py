from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.interactions.models import Responsible


class ResponsibleFilter(SearchFilterMixin):
    """Фильтр истории назначений ответственных."""

    interaction__ids = UUIDInFilter(
        field_name="interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий через запятую"),
    )
    contract__ids = UUIDInFilter(
        field_name="contract",
        label=_("Договоры"),
        help_text=_("Фильтр по списку ID договоров через запятую"),
    )
    manager__ids = NumberInFilter(
        field_name="manager",
        label=_("Ответственные менеджеры"),
        help_text=_("Фильтр по списку ID пользователей через запятую"),
    )

    is_current = filters.BooleanFilter(
        method="filter_is_current",
        label=_("Действующее назначение"),
        help_text=_("True — только незакрытые назначения, false — только закрытые"),
    )

    class Meta:
        model = Responsible
        fields = ()

    def filter_is_current(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Фильтрует назначения по наличию даты снятия."""
        return queryset.filter(unassigned_at__isnull=value)
