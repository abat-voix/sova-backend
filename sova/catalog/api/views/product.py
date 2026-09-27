from sova.catalog.api import filters, serializers
from sova.catalog.models import Product
from sova.core.api.views import SovaBaseViewSet
from sova.catalog.api.views.mixins import CatalogPolicyMixin


class ProductViewSet(CatalogPolicyMixin, SovaBaseViewSet):
    """Продукты. Доступны CRUD операции; программы продукта передаются списком id."""

    read_serializer_class = serializers.ProductSerializer
    serializer_class = serializers.WriteProductSerializer
    queryset = (
        Product.objects
        .select_related("vendor")
        .prefetch_related("programs")
    )
    ordering_fields = "__all__"
    search_fields = ("name", "external_code", "vendor__name")
    filterset_class = filters.ProductFilter
