from collections.abc import Iterator
from contextlib import contextmanager

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.core.api.exceptions import ConflictError
from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.exceptions import ContractAlreadyAttachedError
from sova.interactions.models import Contract
from sova.interactions.services import contract_attachment_service


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

    Договор, созданный импортом реестра, существует без взаимодействия («безголовый»). Действие
    `attach-to-new-interaction` создаёт из него взаимодействие: вместе с договором туда переходят его
    направления, программы и продукты. Ответственный назначается только явно (`manager` в запросе);
    `suggested_manager` договора — подсказка по ФИО менеджера из реестра. Ошибка привязки: 409 — договор
    уже привязан (`contract_already_attached`).
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

        Контрагент и комментарий берутся из договора. Ответственный — только `manager` из запроса;
        без него взаимодействие создаётся без ответственного, как и при обычном создании. Процесс
        workflow не запускается — это отдельный запуск процесса.
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
        """Read-представление договора после привязки."""
        contract = self.get_queryset().get(pk=self.kwargs["pk"])
        return Response(
            data=serializers.ContractSerializer(contract, context=self.get_serializer_context()).data,
            status=status.HTTP_200_OK,
        )
