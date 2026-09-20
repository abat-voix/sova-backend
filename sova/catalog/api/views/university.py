from rest_framework.decorators import action
from rest_framework.response import Response

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

    @action(
        detail=False,
        methods=("get",),
        serializer_class=serializers.UniversityMapPointSerializer,
        pagination_class=None,
        filter_backends=(),
        url_path="map",
    )
    def map_points(self, request) -> Response:
        """Возвращает все вузы с координатами в облегчённом формате карты."""
        queryset = (
            self.get_queryset()
            .exclude(lat__isnull=True)
            .exclude(lon__isnull=True)
        )
        queryset = queryset.only("id", "lat", "lon")
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
