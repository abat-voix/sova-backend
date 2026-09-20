from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.processes.models import WorkflowInstance


class WorkflowInstanceFilter(SearchFilterMixin):
    """Фильтр процессов workflow."""

    workflow__ids = UUIDInFilter(
        field_name="workflow",
        label=_("Workflow"),
        help_text=_("Фильтр по списку ID workflow через запятую"),
    )
    interaction__ids = UUIDInFilter(
        field_name="interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий через запятую"),
    )
    university__ids = UUIDInFilter(
        field_name="interaction__university",
        label=_("Вузы"),
        help_text=_("Фильтр по списку ID вузов через запятую; вуз определяется по взаимодействию"),
    )
    created_by__ids = NumberInFilter(
        field_name="created_by",
        label=_("Авторы"),
        help_text=_("Фильтр по списку ID пользователей, запустивших процесс, через запятую"),
    )
    started_at__gte = filters.DateFilter(
        field_name="started_at",
        lookup_expr="date__gte",
        label=_("Запущен с"),
        help_text=_("Начало периода по дате запуска, включительно (ГГГГ-ММ-ДД)"),
    )
    started_at__lte = filters.DateFilter(
        field_name="started_at",
        lookup_expr="date__lte",
        label=_("Запущен по"),
        help_text=_("Конец периода по дате запуска, включительно (ГГГГ-ММ-ДД)"),
    )

    is_completed = filters.BooleanFilter(
        method="filter_is_completed",
        label=_("Завершён"),
        help_text=_("True — только завершённые процессы, false — только незавершённые"),
    )

    class Meta:
        model = WorkflowInstance
        fields = ("status",)

    def filter_is_completed(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Фильтрует процессы по наличию даты завершения."""
        return queryset.filter(completed_at__isnull=not value)
