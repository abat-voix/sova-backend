from django.db.models import Count

from sova.catalog.api import filters, serializers
from sova.catalog.models import Program
from sova.core.api.views import SovaBaseViewSet
from sova.catalog.api.views.mixins import CatalogPolicyMixin, CatalogRankMixin


class ProgramViewSet(CatalogPolicyMixin, CatalogRankMixin, SovaBaseViewSet):
    """Программы. Доступны CRUD операции, в списке — число продуктов программы."""

    read_serializer_class = serializers.ProgramSerializer
    serializer_class = serializers.WriteProgramSerializer
    queryset = (
        Program.objects
        .select_related("direction")
        .annotate(products_count=Count("products", distinct=True))
        .order_by("name")  # annotate() со GROUP BY сбрасывает Meta.ordering
    )
    ordering_fields = "__all__"
    search_fields = ("name", "direction__name")
    filterset_class = filters.ProgramFilter
