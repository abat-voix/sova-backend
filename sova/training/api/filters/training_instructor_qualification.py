from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.training.models import TrainingInstructorQualification


class TrainingInstructorQualificationFilter(SearchFilterMixin):
    """Фильтр записей о подготовке преподавателей."""

    instructor__ids = UUIDInFilter(
        field_name="instructor",
        label=_("Преподаватели"),
        help_text=_("Фильтр по списку ID преподавателей через запятую"),
    )
    program__ids = UUIDInFilter(
        field_name="program",
        label=_("Программы"),
        help_text=_("Фильтр по списку ID программ через запятую"),
    )
    completed_from = filters.DateFilter(field_name="completed_at", lookup_expr="gte", label=_("Завершено с"))
    completed_to = filters.DateFilter(field_name="completed_at", lookup_expr="lte", label=_("Завершено по"))

    class Meta:
        model = TrainingInstructorQualification
        fields = ("kind",)
