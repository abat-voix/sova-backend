from sova.core.api.views import ReadWriteCreateModelMixin, SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.models import WorkflowInstance


class WorkflowInstanceViewSet(ReadWriteCreateModelMixin, SovaReadOnlyViewSet):
    """
    Процессы workflow: просмотр и запуск.

    Смена статуса, переходы между этапами и завершение процесса не реализованы
    и в API пока недоступны.
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
        """Привязка текущего пользователя при запуске процесса."""
        serializer.save(created_by=self.request.user)
