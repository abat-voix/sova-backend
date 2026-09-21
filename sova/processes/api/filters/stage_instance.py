from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.processes.models import StageInstance


class StageInstanceFilter(SearchFilterMixin):
    """Фильтр экземпляров этапов."""

    workflow_instance__ids = UUIDInFilter(
        field_name="workflow_instance",
        label=_("Процессы"),
        help_text=_("Фильтр по списку ID процессов workflow через запятую"),
    )
    interaction__ids = UUIDInFilter(
        field_name="workflow_instance__interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий через запятую; определяется по процессу"),
    )
    stage__ids = UUIDInFilter(
        field_name="stage",
        label=_("Этапы"),
        help_text=_("Фильтр по списку ID этапов workflow через запятую"),
    )
    context_id = filters.UUIDFilter(
        field_name="context_id",
        label=_("ID контекста"),
        help_text=_("Используется вместе с context_type: ID взаимодействия, направления, программы или продукта"),
    )

    is_completed = filters.BooleanFilter(
        method="filter_is_completed",
        label=_("Завершён"),
        help_text=_("True — только завершённые этапы, false — только незавершённые"),
    )

    class Meta:
        model = StageInstance
        fields = (
            "context_type",
            "status",
        )

    def filter_is_completed(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Фильтрует экземпляры этапов по наличию даты завершения."""
        return queryset.filter(completed_at__isnull=not value)
