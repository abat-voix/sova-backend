from sova.catalog.api import filters, serializers
from sova.catalog.models import B2CClient
from sova.core.api.views import SovaBaseViewSet


class B2CClientViewSet(SovaBaseViewSet):
    """B2C-клиенты (физ/юрлица вне вузовской сети). Доступны CRUD операции."""

    read_serializer_class = serializers.B2CClientSerializer
    serializer_class = serializers.WriteB2CClientSerializer
    queryset = B2CClient.objects.all()
    ordering_fields = "__all__"
    search_fields = ("full_name", "inn", "email", "phone")
    filterset_class = filters.B2CClientFilter
