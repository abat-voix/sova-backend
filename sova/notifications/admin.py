from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin, AbstractHistoryModelAdmin
from sova.notifications.models import DeadlineDelivery, Notification, NotificationProfile, NotifySettings


@admin.register(Notification)
class NotificationAdmin(AbstractBaseModelAdmin[Notification]):
    """Уведомления в системе: создаёт системный канал, вручную не заводятся."""

    list_display = ("title", "kind", "recipient", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    list_select_related = ("recipient",)
    search_fields = ("title", "text", "recipient__email", "recipient__last_name")
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(NotificationProfile)
class NotificationProfileAdmin(AbstractBaseModelAdmin[NotificationProfile]):
    """Админка контактов пользователя для уведомлений."""

    list_display = ("id", "user", "email", "telegram_chat_id", "max_chat_id")
    list_select_related = ("user",)
    search_fields = ("id", "email", "user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)


@admin.register(NotifySettings)
class NotifySettingsAdmin(AbstractBaseModelAdmin[NotifySettings]):
    """Настройки типов уведомлений: строки из миграции, только редактирование."""

    list_display = ("notify_type", "is_enabled", "is_notify_responsible", "is_notify_head", "delivery_mode")
    readonly_fields = ("notify_type",)
    fieldsets = (
        (None, {"fields": ("notify_type", "is_enabled")}),
        ("Получатели", {"fields": ("is_notify_responsible", "is_notify_head", "head_mode")}),
        (
            "Каналы",
            {"fields": ("is_channel_email", "is_channel_telegram", "is_channel_max", "is_channel_system")},
        ),
        (
            "Только для сроков",
            {
                "fields": (
                    "remind_before_days",
                    "is_remind_responsible",
                    "is_remind_head",
                    "repeat_every_days",
                    "delivery_mode",
                    "is_skip_weekends",
                    "is_fallback_to_head",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DeadlineDelivery)
class DeadlineDeliveryAdmin(AbstractHistoryModelAdmin[DeadlineDelivery]):
    """Журнал уведомлений о сроках: пишет задача notify_deadlines, вручную не редактируется."""

    list_display = ("notify_type", "event", "channel", "object_id", "deadline", "recipient", "last_sent_at", "send_count")
    list_filter = ("notify_type", "event", "channel")
    list_select_related = ("recipient",)
    search_fields = ("object_id", "recipient__email", "recipient__last_name")
