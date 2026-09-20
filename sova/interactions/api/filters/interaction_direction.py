from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.interactions.models import InteractionDirection


class InteractionDirectionFilter(SearchFilterMixin):
    """Фильтр направлений взаимодействия."""

    interaction__ids = UUIDInFilter(
        field_name="interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий через запятую"),
    )
    it_direction__ids = UUIDInFilter(
        field_name="it_direction",
        label=_("ИТ-направления"),
        help_text=_("Фильтр по списку ID ИТ-направлений через запятую"),
    )

    class Meta:
        model = InteractionDirection
        fields = ("is_active",)
