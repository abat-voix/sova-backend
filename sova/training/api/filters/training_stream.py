from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.training.models import TrainingStream


class TrainingStreamFilter(SearchFilterMixin):
    """Фильтр потоков обучения."""

    interaction_program__ids = UUIDInFilter(
        field_name="interaction_program",
        label=_("Программы взаимодействий"),
        help_text=_("Фильтр по списку ID программ взаимодействий через запятую"),
    )
    interaction__ids = UUIDInFilter(
        field_name="interaction_program__interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий через запятую"),
    )
    program__ids = UUIDInFilter(
        field_name="interaction_program__program",
        label=_("Программы"),
        help_text=_("Фильтр по списку ID программ каталога через запятую"),
    )

    class Meta:
        model = TrainingStream
        fields = ("status",)
