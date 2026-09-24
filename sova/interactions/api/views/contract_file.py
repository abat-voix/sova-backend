from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import action

from sova.core.api.views import SovaReadOnlyViewSet
from sova.core.files import file_response
from sova.interactions.api import filters, serializers
from sova.interactions.models import ContractFile
from sova.interactions.services import visible_contracts

_DOWNLOAD_RESPONSES = {
    (200, "application/octet-stream"): OpenApiResponse(OpenApiTypes.BINARY),
    302: OpenApiResponse(description="Редирект на подписанный URL (S3_DOWNLOAD_MODE=redirect)"),
    404: OpenApiResponse(description="Файл не найден или недоступен"),
    410: OpenApiResponse(description="Файл больше недоступен в хранилище"),
}


class ContractFileViewSet(SovaReadOnlyViewSet):
    """
    Журнал файлов договора — только чтение: список (с фильтром по `contract`) и скачивание.

    Записи создаются системой при загрузке файла в договор (`ContractViewSet`), а не через
    этот эндпоинт — П9 «история не удаляется».
    """

    read_serializer_class = serializers.ContractFileSerializer
    serializer_class = serializers.ContractFileSerializer
    queryset = ContractFile.objects.select_related("contract", "uploaded_by")
    ordering_fields = ("uploaded_at",)
    filterset_class = filters.ContractFileFilter

    def get_queryset(self) -> QuerySet:
        """Только файлы видимых пользователю договоров (см. `visible_contracts`)."""
        return super().get_queryset().filter(contract__in=visible_contracts(self.request.user))

    @extend_schema(responses=_DOWNLOAD_RESPONSES)
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Скачивание конкретной (в т. ч. прежней) версии файла договора."""
        contract_file = self.get_object()
        return file_response(contract_file.file, contract_file.original_name or contract_file.file.name)
