from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from accounts.policy import Action
from sova.catalog.api import serializers
from sova.catalog.api.views.mixins import ImportResponseMixin
from sova.catalog.exceptions import CatalogImportError
from sova.catalog.services import catalog_import_service, import_file_service


class CatalogImportViewSet(ImportResponseMixin, GenericViewSet):
    """
    Загрузка каталога или реестра договоров из xlsx/xls.

    Колонки файла переводятся в поля через маппинг выбранного типа (/api/catalog/import-mappings/).
    Импорт — всё или ничего: при любой ошибке ничего не сохраняется, в ответе — все ошибки строк.
    Успешный импорт может вернуть предупреждения (`warnings`): строки загружены, но часть данных не
    применена — например, менеджер из реестра не найден среди КАМов и не назначен ответственным.
    """

    serializer_class = serializers.CatalogImportSerializer
    parser_classes = (MultiPartParser,)
    policy_actions = {"create": Action.CATALOG_IMPORT, "read_headers": Action.CATALOG_IMPORT}

    @extend_schema(
        request=serializers.CatalogImportSerializer,
        responses={
            200: serializers.CatalogImportResultSerializer,
            400: serializers.CatalogImportErrorSerializer,
        },
    )
    def create(self, request) -> Response:
        """Импортирует файл и возвращает число созданных и обновлённых записей и предупреждения."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        return self.import_response(
            run=lambda: catalog_import_service.import_file(
                catalog_type=validated_data["catalog_type"],
                source=validated_data["file"],
                user=request.user,
            ),
            data=lambda result: serializers.CatalogImportResultSerializer(
                {
                    "catalog_type": validated_data["catalog_type"],
                    "created": result.created,
                    "updated": result.updated,
                    "warnings": self.import_warnings(result.warnings),
                }
            ).data,
        )

    @extend_schema(
        request=serializers.CatalogImportHeadersSerializer,
        responses={
            200: serializers.CatalogImportHeadersResultSerializer,
            400: serializers.CatalogImportErrorSerializer,
        },
    )
    @action(
        methods=["POST"],
        detail=False,
        url_path="headers",
        url_name="headers",
        serializer_class=serializers.CatalogImportHeadersSerializer,
    )
    def read_headers(self, request) -> Response:
        """Заголовки файла для настройки маппинга; ничего не импортирует."""
        # Не `headers`: так в DRF называется атрибут view с заголовками ответа
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            headers = import_file_service.read_headers(source=serializer.validated_data["file"])
        except CatalogImportError as error:
            return Response(
                data=serializers.CatalogImportErrorSerializer({"detail": str(error), "code": "import_error"}).data,
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            data=serializers.CatalogImportHeadersResultSerializer({"headers": headers}).data,
            status=status.HTTP_200_OK,
        )
