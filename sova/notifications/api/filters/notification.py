from sova.core.api.filters import SearchFilterMixin
from sova.notifications.models import Notification


class NotificationFilter(SearchFilterMixin):
    """Фильтр уведомлений в системе."""

    class Meta:
        model = Notification
        fields = ("is_read", "kind")
