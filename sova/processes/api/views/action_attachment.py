from sova.core.api.views import ReadWriteCreateModelMixin, SovaReadOnlyViewSet
from sova.processes.api import filters, serializers
from sova.processes.models import ActionAttachment


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

    def perform_create(self, serializer: serializers.WriteActionAttachmentSerializer) -> None:
        """Привязка текущего пользователя при загрузке файла."""
        serializer.save(uploaded_by=self.request.user)
