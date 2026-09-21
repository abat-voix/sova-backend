from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.interactions.models import InteractionProgram


class InteractionProgramFilter(SearchFilterMixin):
    """Фильтр программ взаимодействия."""

    interaction__ids = UUIDInFilter(
        field_name="interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий через запятую"),
    )
    program__ids = UUIDInFilter(
        field_name="program",
        label=_("Программы"),
        help_text=_("Фильтр по списку ID программ через запятую"),
    )
    direction__ids = UUIDInFilter(
        field_name="program__direction",
        label=_("Направления"),
        help_text=_(
            "Фильтр по списку ID направлений через запятую; "
            "направление определяется по каталожной программе",
        ),
    )

    class Meta:
        model = InteractionProgram
        fields = ("is_active",)
