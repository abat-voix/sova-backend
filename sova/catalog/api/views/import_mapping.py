from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api import filters, serializers
from sova.catalog.enum import CatalogType
from sova.catalog.exceptions import CatalogImportMappingError
from sova.catalog.models import CatalogImportMapping
from sova.catalog.schemas import CATALOG_IMPORT_FIELD_LABELS, CATALOG_IMPORT_FIELDS
from sova.catalog.services import MappingField, catalog_import_mapping_service
from sova.core.api.views import SovaReadOnlyViewSet

_CATALOG_TYPE_PARAMETER = OpenApiParameter(
    name="catalog_type",
    type=str,
    location=OpenApiParameter.PATH,
    enum=CatalogType.values,
    description="Тип каталога",
)


class CatalogImportMappingViewSet(SovaReadOnlyViewSet):
    """
    Маппинг колонок файлов импорта на канонические поля. Доступно только чтение по записям.

    Одна запись — одна колонка одного catalog_type. Маппинг типа читается и меняется целиком
    через /by-type/{catalog_type}/; допустимые target_field типа — в /fields/.
    """

    read_serializer_class = serializers.CatalogImportMappingSerializer
    serializer_class = serializers.CatalogImportMappingSerializer
    queryset = CatalogImportMapping.objects.all()
    ordering_fields = "__all__"
    search_fields = ("source_column", "target_field")
    filterset_class = filters.CatalogImportMappingFilter
    # Маппинг нужен только тому, кто загружает файлы, — чтение закрыто тем же правом, что и изменение
    policy_actions = {
        "list": Action.CATALOG_MAPPINGS_MANAGE,
        "retrieve": Action.CATALOG_MAPPINGS_MANAGE,
        "available_fields": Action.CATALOG_MAPPINGS_MANAGE,
        "by_type": Action.CATALOG_MAPPINGS_MANAGE,
    }

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

        data = [
            {"name": name, "label": CATALOG_IMPORT_FIELD_LABELS[name], "required": True}
            for name in sorted(fields.required)
        ]
        data += [
            {"name": name, "label": CATALOG_IMPORT_FIELD_LABELS[name], "required": False}
            for name in sorted(fields.optional)
        ]
        return Response(
            data=self.get_serializer(data, many=True).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        methods=["GET"],
        parameters=[_CATALOG_TYPE_PARAMETER],
        responses={200: serializers.CatalogImportTypeMappingFieldSerializer(many=True)},
    )
    @extend_schema(
        methods=["PUT"],
        parameters=[_CATALOG_TYPE_PARAMETER],
        request=serializers.WriteCatalogImportTypeMappingSerializer,
        responses={200: serializers.CatalogImportTypeMappingFieldSerializer(many=True)},
    )
    @action(
        methods=["GET", "PUT"],
        detail=False,
        url_path="by-type/(?P<catalog_type>[^/.]+)",
        serializer_class=serializers.WriteCatalogImportTypeMappingSerializer,
        url_name="by-type",
        filter_backends=(),
        pagination_class=None,
    )
    def by_type(self, request, catalog_type: str) -> Response:
        """
        Маппинг типа целиком: все канонические поля (сначала обязательные) с текущими колонками файла.

        PUT заменяет маппинг типа атомарно; ошибки — в `mappings` по каноническим ключам.
        """
        if catalog_type not in CatalogType.values:
            raise Http404

        if request.method == "GET":
            return self._by_type_response(fields=catalog_import_mapping_service.get_for_type(catalog_type=catalog_type))

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            fields = catalog_import_mapping_service.replace_for_type(
                catalog_type=catalog_type,
                mappings=serializer.validated_data["mappings"],
            )
        except CatalogImportMappingError as error:
            # Формат как у ошибок полей DRF: {ключ: [сообщение]}.
            errors = {target_field: [message] for target_field, message in error.errors.items()}
            raise drf_serializers.ValidationError({"mappings": errors}) from error
        return self._by_type_response(fields=fields)

    def _by_type_response(self, fields: list[MappingField]) -> Response:
        """Ответ by-type: канонические поля типа с колонками файла."""
        return Response(
            data=serializers.CatalogImportTypeMappingFieldSerializer(fields, many=True).data,
            status=status.HTTP_200_OK,
        )
