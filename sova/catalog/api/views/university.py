from sova.catalog.api import filters, serializers
from sova.catalog.models import University
from sova.core.api.views import SovaBaseViewSet


class UniversityViewSet(SovaBaseViewSet):
    """Вузы. Доступны CRUD операции."""

    read_serializer_class = serializers.UniversitySerializer
    serializer_class = serializers.WriteUniversitySerializer
    queryset = University.objects.all()
    ordering_fields = "__all__"
    search_fields = ("name", "inn", "external_code", "email")
    filterset_class = filters.UniversityFilter
