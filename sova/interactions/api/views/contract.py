from django.db import transaction
from django.db.models import QuerySet
from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import action

from sova.core.api.views import SovaBaseViewSet
from sova.core.files import file_response
from sova.interactions.api import filters, serializers
from sova.interactions.models import Contract
from sova.interactions.services import visible_interactions
from sova.interactions.services.contract_files import record_contract_file

_DOWNLOAD_RESPONSES = {
    (200, "application/octet-stream"): OpenApiResponse(OpenApiTypes.BINARY),
    302: OpenApiResponse(description="Редирект на подписанный URL (S3_DOWNLOAD_MODE=redirect)"),
    404: OpenApiResponse(description="Договор не найден, недоступен или без файла"),
    410: OpenApiResponse(description="Файл больше недоступен в хранилище"),
}


class ContractViewSet(SovaBaseViewSet):
    """Договоры. Доступны CRUD операции; файл договора передаётся как multipart."""

    read_serializer_class = serializers.ContractSerializer
    serializer_class = serializers.WriteContractSerializer
    queryset = Contract.objects.select_related(
        "interaction__university",
        "interaction__b2c_client",
    )
    ordering_fields = "__all__"
    search_fields = ("contract_number",)
    filterset_class = filters.ContractFilter

    def get_queryset(self) -> QuerySet:
        """Только договоры видимых пользователю взаимодействий."""
        return super().get_queryset().filter(
            interaction__in=visible_interactions(self.request.user),
        )

    @extend_schema(responses=_DOWNLOAD_RESPONSES)
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Скачивание текущего файла договора под исходным именем."""
        contract = self.get_object()
        if not contract.file:
            raise Http404
        return file_response(contract.file, contract.file_name or contract.file.name)

    @transaction.atomic
    def perform_create(self, serializer: serializers.WriteContractSerializer) -> None:
        """Создание договора; загруженный файл сразу попадает в журнал `ContractFile`."""
        serializer.save()
        if serializer.validated_data.get("file"):
            record_contract_file(serializer.instance, self.request.user)

    @transaction.atomic
    def perform_update(self, serializer: serializers.WriteContractSerializer) -> None:
        """
        Обновление договора; новый файл (создание/корректировка/подписание — см. presets)
        добавляет запись в журнал, не заменяя прежние.
        """
        serializer.save()
        if serializer.validated_data.get("file"):
            record_contract_file(serializer.instance, self.request.user)
