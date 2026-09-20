from sova.catalog.api import filters, serializers
from sova.catalog.models import ITDirection
from sova.core.api.views import SovaBaseViewSet


class ITDirectionViewSet(SovaBaseViewSet):
    """ИТ-направления обучения. Доступны CRUD операции."""

    read_serializer_class = serializers.ITDirectionSerializer
    serializer_class = serializers.WriteITDirectionSerializer
    queryset = ITDirection.objects.all()
    ordering_fields = "__all__"
    search_fields = ("name", "external_code")
    filterset_class = filters.ITDirectionFilter
