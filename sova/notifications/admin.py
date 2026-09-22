from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin
from sova.notifications.models import NotificationProfile


@admin.register(NotificationProfile)
class NotificationProfileAdmin(AbstractBaseModelAdmin[NotificationProfile]):
    """Админка контактов пользователя для уведомлений."""

    list_display = ("id", "user", "email", "telegram_chat_id", "max_chat_id")
    list_select_related = ("user",)
    search_fields = ("id", "email", "user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)
