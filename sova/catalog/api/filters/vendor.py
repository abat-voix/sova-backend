from sova.catalog.models import Vendor
from sova.core.api.filters import SearchFilterMixin


class VendorFilter(SearchFilterMixin):
    """Фильтр вендоров."""

    class Meta:
        model = Vendor
        fields = ("is_active",)
        exact_search_fields = ["name", "external_code"]
