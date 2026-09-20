from sova.catalog.models import B2CClient
from sova.core.api.filters import SearchFilterMixin


class B2CClientFilter(SearchFilterMixin):
    """Фильтр B2C-клиентов."""

    class Meta:
        model = B2CClient
        fields = (
            "kind",
            "is_active",
        )
        exact_search_fields = ["inn"]
