from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.interactions.models import ContractFile


class ContractFileSerializer(serializers.ModelSerializer):
    """Файл договора — запись журнала, только для чтения (список и скачивание)."""

    uploaded_by = UserShortSerializer(
        read_only=True,
        label=_("Кто загрузил"),
        help_text=_("Пользователь, загрузивший файл; пусто, если он удалён"),
    )
    is_current = serializers.SerializerMethodField(
        label=_("Текущий файл"),
        help_text=_("True, если это файл, на который сейчас ссылается договор"),
    )

    class Meta:
        model = ContractFile
        fields = (
            "id",
            "contract",
            "original_name",
            "size",
            "content_type",
            "uploaded_at",
            "uploaded_by",
            "is_current",
        )

    def get_is_current(self, obj: ContractFile) -> bool:
        return obj.file.name == obj.contract.file.name
