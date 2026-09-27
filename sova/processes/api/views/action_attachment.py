from django.db.models import QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.decorators import action

from accounts.policy import Action
from sova.core.api.views import ReadWriteCreateModelMixin, SovaReadOnlyViewSet
from sova.core.files import file_response
from sova.interactions.services import visible_interactions
from sova.processes.api import filters, serializers
from sova.processes.models import ActionAttachment

_DOWNLOAD_RESPONSES = {
    (200, "application/octet-stream"): OpenApiResponse(OpenApiTypes.BINARY),
    302: OpenApiResponse(description="Редирект на подписанный URL (S3_DOWNLOAD_MODE=redirect)"),
    404: OpenApiResponse(description="Вложение не найдено или недоступно"),
    410: OpenApiResponse(description="Файл больше недоступен в хранилище"),
}


class ActionAttachmentViewSet(ReadWriteCreateModelMixin, SovaReadOnlyViewSet):
    """
    Вложения действий — журнал: загрузка (multipart) и просмотр.

    Допустимые форматы файлов заданы ТЗ; записи не редактируются и не удаляются.
    """

    read_serializer_class = serializers.ActionAttachmentSerializer
    serializer_class = serializers.WriteActionAttachmentSerializer
    queryset = ActionAttachment.objects.select_related("uploaded_by")
    ordering_fields = "__all__"
    search_fields = ("file",)
    filterset_class = filters.ActionAttachmentFilter
    policy_actions = {
        "list": Action.PROCESSES_READ,
        "retrieve": Action.PROCESSES_READ,
        "download": Action.PROCESSES_READ,
        "create": Action.PROCESSES_ATTACHMENTS_UPLOAD,
    }

    def get_queryset(self) -> QuerySet:
        """
        Только вложения видимых пользователю взаимодействий.

        Без этого фильтра любой авторизованный пользователь видел бы вложения всех КАМов —
        `ActionAttachment` сам по себе не хранит взаимодействие, поэтому фильтр идёт через
        цепочку `action_instance → stage_instance → workflow_instance → interaction`.
        """
        return super().get_queryset().filter(
            action_instance__stage_instance__workflow_instance__interaction__in=(
                visible_interactions(self.request.user)
            ),
        )

    def perform_create(self, serializer: serializers.WriteActionAttachmentSerializer) -> None:
        """
        Привязка текущего пользователя при загрузке файла.

        `action_instance` берётся из `get_queryset()`-ограниченного набора действий через
        валидатор поля (см. `WriteActionAttachmentSerializer`), поэтому вложение нельзя
        привязать к действию из невидимого взаимодействия.
        """
        serializer.save(uploaded_by=self.request.user)

    @extend_schema(responses=_DOWNLOAD_RESPONSES)
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Скачивание файла вложения под исходным именем."""
        attachment = self.get_object()
        return file_response(attachment.file, attachment.original_name or attachment.file.name)
