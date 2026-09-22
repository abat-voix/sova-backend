from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.catalog.api import filters, serializers
from sova.catalog.models import CatalogImportMapping
from sova.catalog.schemas import CATALOG_IMPORT_FIELDS
from sova.core.api.views import SovaBaseViewSet


class CatalogImportMappingViewSet(SovaBaseViewSet):
    """
    Маппинг колонок файлов импорта на канонические поля. Доступны CRUD операции.

    Одна запись — одна колонка одного catalog_type. Допустимые target_field типа — в /fields/.
    """

    read_serializer_class = serializers.CatalogImportMappingSerializer
    serializer_class = serializers.WriteCatalogImportMappingSerializer
    queryset = CatalogImportMapping.objects.all()
    ordering_fields = "__all__"
    search_fields = ("source_column", "target_field")
    filterset_class = filters.CatalogImportMappingFilter

    @extend_schema(
        parameters=[serializers.CatalogImportFieldsQuerySerializer],
        responses={200: serializers.CatalogImportFieldSerializer(many=True)},
    )
    @action(
        methods=["GET"],
        detail=False,
        url_path="fields",
        serializer_class=serializers.CatalogImportFieldSerializer,
        url_name="fields",
        filter_backends=(),
        pagination_class=None,
    )
    def available_fields(self, request) -> Response:
        """Допустимые target_field типа каталога: сначала обязательные, затем необязательные."""
        query = serializers.CatalogImportFieldsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        fields = CATALOG_IMPORT_FIELDS[query.validated_data["catalog_type"]]

        data = [{"name": name, "required": True} for name in sorted(fields.required)]
        data += [{"name": name, "required": False} for name in sorted(fields.optional)]
        return Response(
            data=self.get_serializer(data, many=True).data,
            status=status.HTTP_200_OK,
        )
