from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.training.models import TrainingInstructor


class TrainingInstructorFilter(SearchFilterMixin):
    """Фильтр преподавателей."""

    university__ids = UUIDInFilter(
        field_name="university",
        label=_("Вузы"),
        help_text=_("Фильтр по списку ID вузов через запятую"),
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

    class Meta:
        model = TrainingInstructor
        fields = ("is_active", "academic_degree", "academic_title")
