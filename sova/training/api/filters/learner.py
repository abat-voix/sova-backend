from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.training.models import Learner


class LearnerFilter(SearchFilterMixin):
    """Фильтр обучающихся."""

    stream__ids = UUIDInFilter(
        field_name="participations__application__stream",
        distinct=True,
        label=_("Потоки"),
        help_text=_("Фильтр по списку ID потоков через запятую"),
    )

    class Meta:
        model = Learner
        fields = ("is_active",)
