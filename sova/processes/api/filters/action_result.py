from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.processes.models import ActionResult


class ActionResultFilter(SearchFilterMixin):
    """Фильтр результатов действий."""

    action_instance__ids = UUIDInFilter(
        field_name="action_instance",
        label=_("Экземпляры действий"),
        help_text=_("Фильтр по списку ID экземпляров действий через запятую"),
    )
    outcome__ids = UUIDInFilter(
        field_name="outcome",
        label=_("Исходы"),
        help_text=_("Фильтр по списку ID исходов через запятую"),
    )
    created_by__ids = NumberInFilter(
        field_name="created_by",
        label=_("Авторы"),
        help_text=_("Фильтр по списку ID пользователей через запятую"),
    )
    created_at__gte = filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__gte",
        label=_("Зафиксировано с"),
        help_text=_("Начало периода по дате фиксации, включительно (ГГГГ-ММ-ДД)"),
    )
    created_at__lte = filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__lte",
        label=_("Зафиксировано по"),
        help_text=_("Конец периода по дате фиксации, включительно (ГГГГ-ММ-ДД)"),
    )

    class Meta:
        model = ActionResult
        fields = ()
