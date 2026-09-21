from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.models import InteractionDirection


class InteractionDirectionViewSet(SovaBaseViewSet):
    """Направления во взаимодействиях. Доступны CRUD операции."""

    read_serializer_class = serializers.InteractionDirectionSerializer
    serializer_class = serializers.WriteInteractionDirectionSerializer
    queryset = InteractionDirection.objects.select_related("direction")
    ordering_fields = "__all__"
    search_fields = ("direction__name",)
    filterset_class = filters.InteractionDirectionFilter
