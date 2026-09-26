from sova.catalog.models import CatalogImportMapping
from sova.core.api.filters import SearchFilterMixin


class CatalogImportMappingFilter(SearchFilterMixin):
    """Фильтр маппингов импорта каталогов."""

    class Meta:
        model = CatalogImportMapping
        fields = ("catalog_type",)
