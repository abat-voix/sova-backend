from collections.abc import Iterator
from contextlib import contextmanager

from django.db import transaction
from django.db.models import Prefetch, QuerySet
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.core.api.exceptions import ConflictError
from sova.core.api.views import SovaBaseViewSet
from sova.core.files import file_response
from sova.interactions.api import filters, serializers
from sova.interactions.exceptions import ContractAlreadyAttachedError
from sova.interactions.models import Contract, Responsible
from sova.interactions.services import contract_attachment_service, visible_contracts
from sova.interactions.services.contract_files import record_contract_file

_DOWNLOAD_RESPONSES = {
    (200, "application/octet-stream"): OpenApiResponse(OpenApiTypes.BINARY),
    302: OpenApiResponse(description="Редирект на подписанный URL (S3_DOWNLOAD_MODE=redirect)"),
    404: OpenApiResponse(description="Договор не найден, недоступен или без файла"),
    410: OpenApiResponse(description="Файл больше недоступен в хранилище"),
}


@contextmanager
def translate_attachment_errors() -> Iterator[None]:
    """Превращает ошибки привязки договора в ответы API: 409 с машиночитаемым кодом."""
    try:
        yield
    except ContractAlreadyAttachedError as error:
        raise ConflictError(
            detail=_("Договор уже привязан к взаимодействию."),
            code="contract_already_attached",
        ) from error


class ContractViewSet(SovaBaseViewSet):
    """
    Договоры. Доступны CRUD операции; файл договора передаётся как multipart.

    Договор, созданный импортом реестра, существует без взаимодействия («безголовый»); его КАМы из реестра —
    `current_responsibles`. Действие `attach-to-new-interaction` создаёт из него взаимодействие: вместе с договором
    туда переходят его направления, программы, продукты и КАМы; `manager` в запросе добавляет ещё одного.
    Ошибка привязки: 409 — договор уже привязан (`contract_already_attached`).
    """

    read_serializer_class = serializers.ContractSerializer
    serializer_class = serializers.WriteContractSerializer
    queryset = Contract.objects.select_related(
        "interaction__university",
        "interaction__b2c_client",
    )
    ordering_fields = "__all__"
    search_fields = ("contract_number",)
    filterset_class = filters.ContractFilter

    @extend_schema(
        request=serializers.AttachToNewInteractionSerializer,
        responses={200: serializers.ContractSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        url_path="attach-to-new-interaction",
        serializer_class=serializers.AttachToNewInteractionSerializer,
    )
    def attach_to_new_interaction(self, request, pk=None) -> Response:
        """
        Создаёт взаимодействие из договора и привязывает к нему договор.

        Контрагент и комментарий берутся из договора. Ответственные — КАМы договора и `manager` из запроса,
        если передан. Процесс workflow не запускается — это отдельный запуск процесса.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic(), translate_attachment_errors():
            contract = self._lock_contract()
            contract_attachment_service.attach_to_new_interaction(
                contract=contract,
                assigned_by=request.user,
                manager=serializer.validated_data.get("manager"),
            )

        return self._contract_response()

    def _lock_contract(self) -> Contract:
        """Блокирует договор на время привязки: две одновременные привязки не пройдут обе."""
        contract = self.get_object()
        return Contract.objects.select_for_update().get(pk=contract.pk)

    def _contract_response(self) -> Response:
        """
        Read-представление договора после привязки.

        Без фильтра видимости: с новым КАМом договор может стать чужим для привязавшего, но ответ о
        выполненной привязке он получить должен.
        """
        contract = self._with_responsibles(super().get_queryset()).get(pk=self.kwargs["pk"])
        return Response(
            data=serializers.ContractSerializer(contract, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )

    def get_queryset(self) -> QuerySet:
        """Только видимые пользователю договоры, включая безголовые (см. `visible_contracts`), с их КАМами."""
        return self._with_responsibles(super().get_queryset().filter(pk__in=visible_contracts(self.request.user)))

    @staticmethod
    def _with_responsibles(queryset: QuerySet) -> QuerySet:
        """Подгружает действующих КАМов headless-договора для `current_responsibles`."""
        return queryset.prefetch_related(
            Prefetch(
                "responsibles",
                queryset=Responsible.objects.filter(
                    interaction__isnull=True,
                    unassigned_at__isnull=True,
                ).select_related("manager").order_by("assigned_at", "pk"),
                to_attr="current_responsibles",
            ),
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
