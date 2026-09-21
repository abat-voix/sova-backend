from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.core.api.views import SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.api.errors import translate_engine_errors
from sova.processes.models import ActionInstance
from sova.processes.services import workflow_engine_service


class ActionInstanceViewSet(SovaReadOnlyViewSet):
    """
    Экземпляры действий этапа: просмотр, завершение и откат.

    Создаёт и меняет экземпляры только движок: действия появляются при запуске процесса, запускаются
    по зависимостям и переходам, завершаются запросом `complete`, откатываются запросом `cancel`.
    """

    serializer_class = serializers.ActionInstanceSerializer
    queryset = ActionInstance.objects.select_related("action", "responsible")
    ordering_fields = "__all__"
    search_fields = ("action_name_snapshot", "status")
    filterset_class = filters.ActionInstanceFilter

    @extend_schema(
        request=serializers.CompleteActionSerializer,
        responses={200: serializers.CompleteActionResultSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.CompleteActionSerializer,
    )
    def complete(self, request, pk=None) -> Response:
        """
        Завершает действие с выбранным исходом и двигает процесс.

        Ответ описывает, что изменилось: результат, запущенные действия, открытые и закрытые этапы, завершён ли
        процесс. Ошибки: 409 (`invalid_state`) — действие не в работе; 400 — нарушены правила исхода
        (`outcome_mismatch`, `outcome_inactive`, `is_comment_required`, `is_attachment_required`).
        """
        action_instance = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with translate_engine_errors():
            outcome = workflow_engine_service.complete_action(
                action_instance=action_instance,
                outcome=serializer.validated_data["outcome"],
                comment=serializer.validated_data["comment"],
                completed_by=request.user,
            )

        return Response(
            data=serializers.CompleteActionResultSerializer(
                outcome,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        request=serializers.CancelActionSerializer,
        responses={200: serializers.CancelActionResultSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.CancelActionSerializer,
    )
    def cancel(self, request, pk=None) -> Response:
        """
        Откатывает выполненное действие: новое исполнение вместо отменённого.

        Откатить можно только последнее исполнение, и только если от него не зависит уже выполненное действие
        того же этапа. Если действие закрыло свой этап, сначала откатывают сам этап. Ошибки: 409 (`invalid_state`)
        — действие не выполнено, не последнее исполнение или этап не в работе; 400 (`has_completed_dependent`) —
        от действия зависит уже выполненное действие.
        """
        action_instance = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with translate_engine_errors():
            outcome = workflow_engine_service.cancel_action(
                action_instance=action_instance,
                reason=serializer.validated_data["reason"],
                cancelled_by=request.user,
            )

        return Response(
            data=serializers.CancelActionResultSerializer(
                outcome,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
