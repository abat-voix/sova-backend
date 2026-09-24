from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.core.api.views import SovaReadOnlyViewSet
from sova.notifications.api import filters, serializers
from sova.notifications.models import Notification
from sova.notifications.services.inbox import kind_summary


class NotificationViewSet(SovaReadOnlyViewSet):
    """Уведомления в системе текущего пользователя: список, счётчик непрочитанных, прочтение."""

    serializer_class = serializers.NotificationSerializer
    queryset = Notification.objects.all()
    ordering_fields = ("created_at", "is_read")
    search_fields = ("title", "text")
    filterset_class = filters.NotificationFilter

    def get_queryset(self) -> QuerySet:
        """Только уведомления текущего пользователя."""
        return super().get_queryset().filter(recipient=self.request.user)

    @extend_schema(responses=serializers.NotificationKindSerializer(many=True))
    @action(detail=False, methods=["get"], pagination_class=None)
    def kinds(self, request):
        """Все группы уведомлений со счётчиками — фронт строит из них фильтры, не зная групп заранее."""
        summary = kind_summary(queryset=self.get_queryset())
        return Response(serializers.NotificationKindSerializer(summary, many=True).data)

    @extend_schema(responses=serializers.UnreadCountSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        """Число непрочитанных уведомлений — для значка колокольчика."""
        count = self.get_queryset().filter(is_read=False).count()
        return Response(serializers.UnreadCountSerializer({"count": count}).data)

    @extend_schema(request=None, responses=serializers.NotificationSerializer)
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        """Отмечает уведомление прочитанным."""
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read", "updated_at"])
        return Response(self.get_serializer(notification).data)

    @extend_schema(request=None, responses=serializers.ReadAllResultSerializer)
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        """Отмечает прочитанными все непрочитанные уведомления пользователя."""
        updated = self.get_queryset().filter(is_read=False).update(is_read=True, updated_at=timezone.now())
        return Response(serializers.ReadAllResultSerializer({"updated": updated}).data)
