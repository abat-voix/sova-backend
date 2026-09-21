from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.core.api.views import ReadWriteCreateModelMixin, SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.api.errors import translate_engine_errors
from sova.processes.models import WorkflowInstance
from sova.processes.services import workflow_board_service, workflow_engine_service


class WorkflowInstanceViewSet(ReadWriteCreateModelMixin, SovaReadOnlyViewSet):
    """
    Процессы workflow: просмотр, запуск и доска.

    Запуск (`POST`) принимает workflow и взаимодействие, остальное создаёт движок: экземпляры этапов и
    действий, открытие начальных этапов. Ошибки: 400 — workflow неактивен, не подходит контрагенту или пуст
    (`workflow_inactive`, `audience_mismatch`, `empty_workflow`); 409 (`already_started`) — этот workflow
    уже запущен для взаимодействия. Состояние процесса дальше меняют только действия над этапами и действиями.
    """

    read_serializer_class = serializers.WorkflowInstanceSerializer
    serializer_class = serializers.WriteWorkflowInstanceSerializer
    queryset = WorkflowInstance.objects.select_related(
        "workflow",
        "interaction__university",
        "interaction__b2c_client",
        "created_by",
    )
    ordering_fields = "__all__"
    search_fields = (
        "status",
        "workflow__name",
        "interaction__university__name",
        "interaction__b2c_client__full_name",
    )
    filterset_class = filters.WorkflowInstanceFilter

    def perform_create(self, serializer: serializers.WriteWorkflowInstanceSerializer) -> None:
        """Запускает процесс через движок от имени текущего пользователя."""
        with translate_engine_errors():
            serializer.instance = workflow_engine_service.start(
                workflow=serializer.validated_data["workflow"],
                interaction=serializer.validated_data["interaction"],
                started_by=self.request.user,
            )

    @extend_schema(
        request=None,
        responses={200: serializers.WorkflowBoardSerializer},
    )
    @action(methods=["GET"], detail=True)
    def board(self, request, pk=None) -> Response:
        """
        Доска процесса: весь путь взаимодействия для визуализации одним ответом.

        Этапы взаимодействия идут по порядку, этапы направлений, программ и продуктов собраны в группы.
        У каждого действия — статус, даты, результат, число вложений и исходы, которые можно выбрать;
        у каждого этапа в работе — этапы, на которые можно вернуться.
        """
        process = self.get_object()

        return Response(
            data=serializers.WorkflowBoardSerializer(
                workflow_board_service.build(process=process),
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
