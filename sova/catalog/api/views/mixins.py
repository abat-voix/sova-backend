from collections.abc import Callable
from typing import TypeVar

from rest_framework import status
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api.serializers import CatalogImportErrorSerializer
from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.schemas import ImportRowWarning

ImportResult = TypeVar("ImportResult")


class CatalogPolicyMixin:
    """Единая политика CRUD для справочников каталога."""

    policy_actions = {
        "list": Action.CATALOG_READ,
        "retrieve": Action.CATALOG_READ,
        "create": Action.CATALOG_CREATE,
        "update": Action.CATALOG_UPDATE,
        "partial_update": Action.CATALOG_UPDATE,
        "destroy": Action.CATALOG_DELETE,
    }


class ImportResponseMixin:
    """
    Ответ загрузки файла — общий для импорта каталогов и обучающихся.

    Загрузка «всё или ничего»: ошибки строк (`CatalogImportRowsError`) — 400 `import_failed` со списком строк,
    ошибка файла целиком (`CatalogImportError`) — 400 `import_error`; успех — 200 с данными, которые собирает
    вызывающий view.
    """

    # Сколько ошибок строк отдавать в ответе: файл с тысячами плохих строк не должен раздувать ответ.
    max_errors_in_response = 100

    def import_response(self, run: Callable[[], ImportResult], data: Callable[[ImportResult], dict]) -> Response:
        """Выполняет `run` и отдаёт `data(result)` либо ошибки импорта в едином формате."""
        try:
            result = run()
        except CatalogImportRowsError as error:
            return Response(
                data=CatalogImportErrorSerializer(
                    {
                        "detail": f"Импорт отменён, ошибок: {len(error.errors)}",
                        "code": "import_failed",
                        "errors": [
                            {"row": row_error.row_number, "message": row_error.message}
                            for row_error in error.errors[: self.max_errors_in_response]
                        ],
                        "errors_total": len(error.errors),
                    }
                ).data,
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CatalogImportError as error:
            return Response(
                data=CatalogImportErrorSerializer({"detail": str(error), "code": "import_error"}).data,
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(data=data(result), status=status.HTTP_200_OK)

    @staticmethod
    def import_warnings(warnings: list[ImportRowWarning]) -> list[dict]:
        """Предупреждения по строкам в формате ответа импорта."""
        return [{"row": warning.row_number, "message": warning.message} for warning in warnings]
