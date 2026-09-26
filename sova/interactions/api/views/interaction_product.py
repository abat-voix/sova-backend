from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.api.views.mixins import InteractionPartMixin, SyncProcessesMixin
from sova.interactions.models import InteractionProduct


class InteractionProductViewSet(InteractionPartMixin, SyncProcessesMixin, SovaBaseViewSet):
    """
    Продукты во взаимодействиях. Доступны CRUD операции.

    Видны и изменяются вместе со взаимодействием (`InteractionPartMixin`). Изменение состава сразу досоздаёт этапы
    в идущих процессах взаимодействия.
    """

    read_serializer_class = serializers.InteractionProductSerializer
    serializer_class = serializers.WriteInteractionProductSerializer
    queryset = InteractionProduct.objects.select_related("product")
    ordering_fields = "__all__"
    search_fields = ("product__name",)
    filterset_class = filters.InteractionProductFilter
