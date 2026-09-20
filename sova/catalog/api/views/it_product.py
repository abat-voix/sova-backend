from sova.catalog.api import filters, serializers
from sova.catalog.models import ITProduct
from sova.core.api.views import SovaBaseViewSet


class ITProductViewSet(SovaBaseViewSet):
    """ИТ-продукты. Доступны CRUD операции; программы продукта передаются списком id."""

    read_serializer_class = serializers.ITProductSerializer
    serializer_class = serializers.WriteITProductSerializer
    queryset = (
        ITProduct.objects
        .select_related("vendor")
        .prefetch_related("programs")
    )
    ordering_fields = "__all__"
    search_fields = ("name", "external_code", "vendor__name")
    filterset_class = filters.ITProductFilter
