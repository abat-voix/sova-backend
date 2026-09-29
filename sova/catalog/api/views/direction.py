from sova.catalog.api import filters, serializers
from sova.catalog.models import Direction
from sova.core.api.views import SovaBaseViewSet
from sova.catalog.api.views.mixins import CatalogPolicyMixin, CatalogRankMixin


class DirectionViewSet(CatalogPolicyMixin, CatalogRankMixin, SovaBaseViewSet):
    """Направления обучения. Доступны CRUD операции."""

    read_serializer_class = serializers.DirectionSerializer
    serializer_class = serializers.WriteDirectionSerializer
    queryset = Direction.objects.all()
    ordering_fields = "__all__"
    search_fields = ("name", "external_code")
    filterset_class = filters.DirectionFilter
