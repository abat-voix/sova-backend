from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.processes.models import ActionAttachment

# Форматы вложений из ТЗ (п. «Возможность прикладывания файлов в статусы»)
ALLOWED_ATTACHMENT_EXTENSIONS = (
    "png",
    "jpg",
    "jpeg",
    "pdf",
    "zip",
    "gz",
    "gzip",
    "rar",
    "doc",
    "docx",
    "xls",
    "xlsx",
)


class ActionAttachmentSerializer(serializers.ModelSerializer):
    """Вложение действия — представление для чтения (list/retrieve)."""

    uploaded_by = UserShortSerializer(
        read_only=True,
        label=_("Кто загрузил"),
        help_text=_("Пользователь, загрузивший файл; пусто, если он удалён"),
    )

    class Meta:
        model = ActionAttachment
        fields = (
            "id",
            "action_instance",
            "file",
            "uploaded_at",
            "uploaded_by",
        )


class WriteActionAttachmentSerializer(serializers.ModelSerializer):
    """
    Вложение действия — валидация входных данных (загрузка файла).

    Формат проверяется по расширению (без учёта регистра, по последнему
    расширению имени файла): содержимое файла не анализируется.
    """

    file = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS)],
        label=_("Файл"),
        help_text=_(
            "Допустимые форматы: png, jpg, jpeg, pdf, zip, gz, gzip, rar, doc, docx, xls, xlsx",
        ),
    )

    class Meta:
        model = ActionAttachment
        fields = (
            "id",
            "action_instance",
            "file",
        )
