from sova.core.api.filters import SearchFilterMixin
from sova.notifications.models import NotificationProfile


class NotificationProfileFilter(SearchFilterMixin):
    """Фильтр профилей уведомлений."""

    class Meta:
        model = NotificationProfile
        fields = ("user",)
