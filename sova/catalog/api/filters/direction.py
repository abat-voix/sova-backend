from sova.catalog.api.filters.rank import RankFilterMixin
from sova.catalog.models import Direction


class DirectionFilter(RankFilterMixin):
    """Фильтр направлений."""

    class Meta:
        model = Direction
        fields = ("is_active",)
        exact_search_fields = ["name", "external_code"]
