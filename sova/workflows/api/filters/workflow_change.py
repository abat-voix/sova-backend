from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.workflows.models import WorkflowChange


class WorkflowChangeFilter(SearchFilterMixin):
    """Фильтр журнала изменений workflow."""

    workflow__ids = UUIDInFilter(
        field_name="workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую"),
    )
    created_by__ids = NumberInFilter(
        field_name="created_by",
        label=_("Авторы"),
        help_text=_("Фильтр по списку ID пользователей через запятую"),
    )
    entity_id = filters.UUIDFilter(
        field_name="entity_id",
        label=_("ID сущности"),
        help_text=_("История изменений конкретной сущности workflow"),
    )
    created_at__gte = filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__gte",
        label=_("Изменено с"),
        help_text=_("Начало периода по дате изменения, включительно (ГГГГ-ММ-ДД)"),
    )
    created_at__lte = filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__lte",
        label=_("Изменено по"),
        help_text=_("Конец периода по дате изменения, включительно (ГГГГ-ММ-ДД)"),
    )

    class Meta:
        model = WorkflowChange
        fields = (
            "change_type",
            "entity_type",
        )
