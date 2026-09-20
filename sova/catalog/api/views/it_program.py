from django.db.models import Count

from sova.catalog.api import filters, serializers
from sova.catalog.models import ITProgram
from sova.core.api.views import SovaBaseViewSet


class ITProgramViewSet(SovaBaseViewSet):
    """ИТ-программы. Доступны CRUD операции, в списке — число продуктов программы."""

    read_serializer_class = serializers.ITProgramSerializer
    serializer_class = serializers.WriteITProgramSerializer
    queryset = (
        ITProgram.objects
        .select_related("it_direction")
        .annotate(products_count=Count("it_products", distinct=True))
        .order_by("name")  # annotate() со GROUP BY сбрасывает Meta.ordering
    )
    ordering_fields = "__all__"
    search_fields = ("name", "it_direction__name")
    filterset_class = filters.ITProgramFilter

    def perform_create(self, serializer: serializers.WriteITProgramSerializer) -> None:
        """Пересоздание инстанса через аннотированный queryset для read-ответа."""
        super().perform_create(serializer)
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)
