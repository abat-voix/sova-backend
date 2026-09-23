from django.contrib import admin

from sova.core.admin import AbstractBaseModelAdmin
from sova.messaging.models import Conversation, ConversationParticipant, Message


class ConversationParticipantInline(admin.TabularInline):
    """Участники беседы прямо в её карточке."""

    model = ConversationParticipant
    extra = 0
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Conversation)
class ConversationAdmin(AbstractBaseModelAdmin[Conversation]):
    """Админка бесед."""

    list_display = ("id", "kind", "dedupe_key", "last_message_at", "created_at")
    list_filter = ("kind",)
    search_fields = ("id", "dedupe_key")
    inlines = (ConversationParticipantInline,)


@admin.register(Message)
class MessageAdmin(AbstractBaseModelAdmin[Message]):
    """Админка сообщений."""

    list_display = ("id", "conversation", "sender", "created_at")
    list_select_related = ("conversation", "sender")
    search_fields = ("id", "text")
    autocomplete_fields = ("conversation", "sender")
