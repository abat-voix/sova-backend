from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.models import InteractionProduct


class InteractionProductViewSet(SovaBaseViewSet):
    """ИТ-продукты во взаимодействиях. Доступны CRUD операции."""

    read_serializer_class = serializers.InteractionProductSerializer
    serializer_class = serializers.WriteInteractionProductSerializer
    queryset = InteractionProduct.objects.select_related("it_product")
    ordering_fields = "__all__"
    search_fields = ("it_product__name",)
    filterset_class = filters.InteractionProductFilter
