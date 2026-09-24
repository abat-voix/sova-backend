from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from sova.catalog.api import serializers
from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.services import catalog_import_service

# Сколько ошибок строк отдавать в ответе: файл с тысячами плохих строк не должен раздувать ответ.
MAX_ERRORS_IN_RESPONSE = 100


class CatalogImportViewSet(GenericViewSet):
    """
    Загрузка каталога или реестра договоров из xlsx/xls.

    Колонки файла переводятся в поля через маппинг выбранного типа (/api/catalog/import-mappings/).
    Импорт — всё или ничего: при любой ошибке ничего не сохраняется, в ответе — все ошибки строк.
    Успешный импорт может вернуть предупреждения (`warnings`): строки загружены, но часть данных не
    применена — например, менеджер из реестра не найден среди КАМов и не назначен ответственным.
    """

    serializer_class = serializers.CatalogImportSerializer
    parser_classes = (MultiPartParser,)

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

        try:
            result = catalog_import_service.import_file(
                catalog_type=validated_data["catalog_type"],
                source=validated_data["file"],
                user=request.user,
            )
        except CatalogImportRowsError as error:
            return Response(
                data=serializers.CatalogImportErrorSerializer(
                    {
                        "detail": f"Импорт отменён, ошибок: {len(error.errors)}",
                        "code": "import_failed",
                        "errors": [
                            {"row": row_error.row_number, "message": row_error.message}
                            for row_error in error.errors[:MAX_ERRORS_IN_RESPONSE]
                        ],
                        "errors_total": len(error.errors),
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CatalogImportError as error:
            return Response(
                data=serializers.CatalogImportErrorSerializer({"detail": str(error), "code": "import_error"}).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            data=serializers.CatalogImportResultSerializer(
                {
                    "catalog_type": validated_data["catalog_type"],
                    "created": result.created,
                    "updated": result.updated,
                    "warnings": [
                        {"row": warning.row_number, "message": warning.message} for warning in result.warnings
                    ],
                }
            ).data,
            status=status.HTTP_200_OK,
        )
