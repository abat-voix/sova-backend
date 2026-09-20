from sova.catalog.api import filters, serializers
from sova.catalog.models import Vendor
from sova.core.api.views import SovaBaseViewSet


class VendorViewSet(SovaBaseViewSet):
    """Вендоры ИТ-продуктов. Доступны CRUD операции."""

    read_serializer_class = serializers.VendorSerializer
    serializer_class = serializers.WriteVendorSerializer
    queryset = Vendor.objects.all()
    ordering_fields = "__all__"
    search_fields = ("name", "external_code")
    filterset_class = filters.VendorFilter
