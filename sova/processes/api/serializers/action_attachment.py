from django.core.validators import FileExtensionValidator
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.core.files import guess_content_type, validate_file_size
from sova.interactions.services import visible_interactions
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
    download_url = serializers.SerializerMethodField(
        label=_("Ссылка на скачивание"),
        help_text=_("Проверяет права и отдаёт файл под исходным именем"),
    )

    class Meta:
        model = ActionAttachment
        fields = (
            "id",
            "action_instance",
            "original_name",
            "size",
            "content_type",
            "download_url",
            "uploaded_at",
            "uploaded_by",
        )

    def get_download_url(self, obj: ActionAttachment) -> str:
        return reverse("processes:action-attachment-download", args=[obj.pk])


class WriteActionAttachmentSerializer(serializers.ModelSerializer):
    """
    Вложение действия — валидация входных данных (загрузка файла).

    Формат проверяется по расширению (без учёта регистра, по последнему
    расширению имени файла): содержимое файла не анализируется.
    """

    file = serializers.FileField(
        validators=[
            FileExtensionValidator(allowed_extensions=ALLOWED_ATTACHMENT_EXTENSIONS),
            validate_file_size,
        ],
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

    def validate_action_instance(self, action_instance):
        """
        Вложение можно привязать только к действию видимого взаимодействия.

        Поле по умолчанию проверяет лишь существование `ActionInstance` (весь набор), а не
        видимость его взаимодействия для текущего пользователя — иначе КАМ мог бы приложить
        файл к чужой заявке, зная её ID.
        """
        request = self.context["request"]
        interaction_id = action_instance.stage_instance.workflow_instance.interaction_id
        is_visible = visible_interactions(request.user).filter(id=interaction_id).exists()
        if not is_visible:
            raise serializers.ValidationError(_("Действие не найдено."), code="not_found")
        return action_instance

    def create(self, validated_data: dict) -> ActionAttachment:
        """Ключ файла — случайный UUID (`uuid_upload_to`); исходное имя и тип — отдельно."""
        uploaded_file = validated_data["file"]
        validated_data["original_name"] = uploaded_file.name
        validated_data["size"] = uploaded_file.size
        validated_data["content_type"] = guess_content_type(uploaded_file.name)
        return super().create(validated_data)
