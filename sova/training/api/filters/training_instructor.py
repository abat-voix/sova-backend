from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.training.models import TrainingInstructor, TrainingStream
from sova.training.services.stream import training_stream_service


class TrainingInstructorFilter(SearchFilterMixin):
    """Фильтр преподавателей."""

    organization__ids = UUIDInFilter(
        field_name="organization",
        label=_("Организации"),
        help_text=_("Фильтр по списку ID организаций через запятую"),
    )
    b2c_client__ids = UUIDInFilter(
        field_name="b2c_client",
        label=_("B2C-клиенты"),
        help_text=_("Фильтр по списку ID B2C-клиентов через запятую"),
    )
    program__ids = UUIDInFilter(
        field_name="programs",
        distinct=True,
        label=_("Программы"),
        help_text=_("Фильтр по списку ID программ через запятую"),
    )
    direction__ids = UUIDInFilter(
        field_name="directions",
        distinct=True,
        label=_("Направления"),
        help_text=_("Фильтр по списку ID направлений через запятую"),
    )
    assignable_to_stream = filters.UUIDFilter(
        method="filter_assignable_to_stream",
        label=_("Можно назначить на поток"),
        help_text=_(
            "ID потока: активные преподаватели контрагента, которые ведут программу потока и ещё не назначены; "
            "для завершённого или отменённого потока — пусто"
        ),
    )

    class Meta:
        model = TrainingInstructor
        fields = ("is_active", "academic_degree", "academic_title")

    def filter_assignable_to_stream(self, queryset: QuerySet, name: str, value) -> QuerySet:
        """Оставляет преподавателей, которых можно назначить на поток."""
        stream = TrainingStream.objects.select_related("interaction_program__interaction").filter(pk=value).first()
        if stream is None:
            return queryset.none()
        return training_stream_service.assignable_instructors(stream, queryset)
