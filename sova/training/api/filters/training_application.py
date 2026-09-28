from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.training.models import TrainingApplication


class TrainingApplicationFilter(SearchFilterMixin):
    """Фильтр заявок."""

    stream__ids = UUIDInFilter(
        field_name="stream",
        label=_("Потоки"),
        help_text=_("Фильтр по списку ID потоков через запятую"),
    )
    learner__ids = UUIDInFilter(
        field_name="participants__learner",
        distinct=True,
        label=_("Обучающиеся"),
        help_text=_("Фильтр по списку ID обучающихся через запятую"),
    )

    class Meta:
        model = TrainingApplication
        fields = ("status",)
