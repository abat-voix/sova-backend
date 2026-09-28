from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.training.models import TrainingApplicationLearner


class TrainingApplicationLearnerFilter(SearchFilterMixin):
    """Фильтр участников заявок."""

    application__ids = UUIDInFilter(
        field_name="application",
        label=_("Заявки"),
        help_text=_("Фильтр по списку ID заявок через запятую"),
    )
    stream__ids = UUIDInFilter(
        field_name="application__stream",
        label=_("Потоки"),
        help_text=_("Фильтр по списку ID потоков через запятую"),
    )
    learner__ids = UUIDInFilter(
        field_name="learner",
        label=_("Обучающиеся"),
        help_text=_("Фильтр по списку ID обучающихся через запятую"),
    )

    class Meta:
        model = TrainingApplicationLearner
        fields = ("is_paid",)
