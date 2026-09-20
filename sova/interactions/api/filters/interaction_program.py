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
    it_program__ids = UUIDInFilter(
        field_name="it_program",
        label=_("ИТ-программы"),
        help_text=_("Фильтр по списку ID ИТ-программ через запятую"),
    )
    it_direction__ids = UUIDInFilter(
        field_name="it_program__it_direction",
        label=_("ИТ-направления"),
        help_text=_(
            "Фильтр по списку ID ИТ-направлений через запятую; "
            "направление определяется по каталожной программе",
        ),
    )

    class Meta:
        model = InteractionProgram
        fields = ("is_active",)
