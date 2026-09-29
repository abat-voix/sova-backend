from sova.catalog.api.filters.rank import RankFilterMixin
from sova.catalog.models import B2CClient


class B2CClientFilter(RankFilterMixin):
    """Фильтр B2C-клиентов."""

    class Meta:
        model = B2CClient
        fields = (
            "is_active",
        )
        exact_search_fields = ["inn"]
