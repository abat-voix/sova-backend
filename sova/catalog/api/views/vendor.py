from sova.catalog.api import filters, serializers
from sova.catalog.models import Vendor
from sova.core.api.views import SovaBaseViewSet
from sova.catalog.api.views.mixins import CatalogPolicyMixin


class VendorViewSet(CatalogPolicyMixin, SovaBaseViewSet):
    """Вендоры продуктов. Доступны CRUD операции."""

    read_serializer_class = serializers.VendorSerializer
    serializer_class = serializers.WriteVendorSerializer
    queryset = Vendor.objects.all()
    ordering_fields = "__all__"
    search_fields = ("name", "external_code")
    filterset_class = filters.VendorFilter
