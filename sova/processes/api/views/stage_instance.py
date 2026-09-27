from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.core.api.views import SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.api.views.mixins import VisibleInteractionMixin
from sova.processes.api.errors import translate_engine_errors
from sova.processes.models import StageInstance
from sova.processes.services import workflow_engine_service


class StageInstanceViewSet(VisibleInteractionMixin, SovaReadOnlyViewSet):
    """
    Экземпляры этапов процесса: просмотр и отмена.

    Экземпляры создаёт и открывает движок; пользователь может только отменить этап в работе — процесс
    вернётся на предыдущий этап.
    """

    serializer_class = serializers.StageInstanceSerializer
    interaction_lookup = "workflow_instance__interaction"
    queryset = StageInstance.objects.select_related("stage", "added_by")
    ordering_fields = "__all__"
    search_fields = ("status", "stage__name")
    filterset_class = filters.StageInstanceFilter
    policy_actions = {
        "list": Action.PROCESSES_READ,
        "retrieve": Action.PROCESSES_READ,
        "cancel": Action.PROCESSES_EXECUTE,
    }

    @extend_schema(
        request=serializers.CancelStageSerializer,
        responses={200: serializers.CancelStageResultSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.CancelStageSerializer,
    )
    def cancel(self, request, pk=None) -> Response:
        """
        Отменяет этап в работе и возвращает процесс на предыдущий этап.

        Если предшественников несколько, этап возврата передаётся в `return_to` (варианты отдаёт доска).
        Ошибки: 409 (`invalid_state`) — этап не в работе; 400 — нарушены правила отката (`no_predecessor`,
        `return_to_required`, `invalid_return_to`, `no_mandatory_action`).
        """
        stage_instance = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with translate_engine_errors():
            outcome = workflow_engine_service.cancel_stage(
                stage_instance=stage_instance,
                mode=serializer.validated_data["mode"],
                reason=serializer.validated_data["reason"],
                cancelled_by=request.user,
                return_to=serializer.validated_data.get("return_to"),
            )

        return Response(
            data=serializers.CancelStageResultSerializer(
                outcome,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
