from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class UserShortSerializer(serializers.ModelSerializer):
    """Пользователь — краткое представление для вложенного использования."""

    full_name = serializers.SerializerMethodField(
        label=_("Полное имя"),
        help_text=_("ФИО пользователя, а при его отсутствии — логин"),
    )

    class Meta:
        model = get_user_model()
        fields = ("id", "email", "full_name")

    def get_full_name(self, instance) -> str:
        """Возвращает ФИО пользователя или логин, если ФИО не заполнено."""
        return instance.get_full_name() or instance.get_username()
