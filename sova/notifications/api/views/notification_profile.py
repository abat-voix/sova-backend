from sova.core.api.views import SovaBaseViewSet
from sova.notifications.api import filters, serializers
from sova.notifications.models import NotificationProfile


class NotificationProfileViewSet(SovaBaseViewSet):
    """Контакты пользователей для уведомлений. Доступны CRUD операции."""

    read_serializer_class = serializers.NotificationProfileSerializer
    serializer_class = serializers.WriteNotificationProfileSerializer
    queryset = NotificationProfile.objects.select_related("user")
    ordering_fields = "__all__"
    search_fields = (
        "email",
        "telegram_chat_id",
        "max_chat_id",
        "user__email",
        "user__first_name",
        "user__last_name",
    )
    filterset_class = filters.NotificationProfileFilter
