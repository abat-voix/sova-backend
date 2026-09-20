from sova.catalog.models import Direction
from sova.core.api.filters import SearchFilterMixin


class DirectionFilter(SearchFilterMixin):
    """Фильтр направлений."""

    class Meta:
        model = Direction
        fields = ("is_active",)
        exact_search_fields = ["name", "external_code"]
