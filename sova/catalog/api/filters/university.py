from sova.catalog.models import University
from sova.core.api.filters import SearchFilterMixin


class UniversityFilter(SearchFilterMixin):
    """Фильтр вузов."""

    class Meta:
        model = University
        fields = ("is_active",)
        exact_search_fields = ["name", "inn", "external_code"]
