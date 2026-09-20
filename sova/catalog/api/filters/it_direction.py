from sova.catalog.models import ITDirection
from sova.core.api.filters import SearchFilterMixin


class ITDirectionFilter(SearchFilterMixin):
    """Фильтр ИТ-направлений."""

    class Meta:
        model = ITDirection
        fields = ("is_active",)
        exact_search_fields = ["name", "external_code"]
