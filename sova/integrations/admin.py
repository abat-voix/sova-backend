import json

from django.contrib import admin, messages
from django.db import transaction

from sova.integrations.enum import IntegrationDirection, IntegrationStatus
from sova.integrations.models import IntegrationMapping, IntegrationMessage
from sova.integrations.services import _schedule


@admin.register(IntegrationMapping)
class IntegrationMappingAdmin(admin.ModelAdmin):
    list_display = ("name", "system", "direction", "entity", "version", "is_active", "updated_at")
    list_filter = ("system", "direction", "entity", "is_active")
    search_fields = ("name", "event_type")
    readonly_fields = ("id", "version", "created_at", "updated_at")


@admin.register(IntegrationMessage)
class IntegrationMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "system", "direction", "event_type", "external_id", "status", "attempts")
    list_filter = ("system", "direction", "status", "event_type")
    search_fields = ("external_id", "correlation_id")
    readonly_fields = (
        "id", "created_at", "updated_at", "system", "direction", "event_type", "external_id",
        "correlation_id", "payload_pretty", "mapping", "result", "status", "attempts", "next_retry_at",
        "last_error", "processed_at",
    )
    fields = readonly_fields
    actions = ("retry_messages",)

    @admin.display(description="Payload")
    def payload_pretty(self, obj):
        return json.dumps(obj.payload, ensure_ascii=False, indent=2, sort_keys=True)

    @admin.action(description="Повторить выбранные сообщения")
    def retry_messages(self, request, queryset):
        count = 0
        for message in queryset.filter(status__in=(IntegrationStatus.FAILED, IntegrationStatus.IGNORED)):
            message.status = IntegrationStatus.PENDING
            message.last_error = ""
            message.next_retry_at = None
            message.processed_at = None
            message.save(update_fields=["status", "last_error", "next_retry_at", "processed_at", "updated_at"])
            transaction.on_commit(lambda message=message: _schedule(message))
            count += 1
        self.message_user(request, f"Поставлено на повтор: {count}", messages.SUCCESS)
