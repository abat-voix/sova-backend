from django.db.models import Count, Q, QuerySet

from sova.notifications.enum import NOTIFICATION_KIND_ICONS, NotificationKind


def kind_summary(queryset: QuerySet) -> list[dict]:
    """
    Все группы уведомлений в порядке NotificationKind с числом уведомлений и непрочитанных из queryset.

    Пустые группы тоже в списке — фронт строит фильтры из ответа и сам решает, скрывать ли нули.
    """
    counts = {
        row["kind"]: row
        for row in queryset.order_by()
        .values("kind")
        .annotate(count=Count("id"), unread_count=Count("id", filter=Q(is_read=False)))
    }
    return [
        {
            "value": kind.value,
            "label": kind.label,
            "icon": NOTIFICATION_KIND_ICONS[kind],
            "count": counts.get(kind.value, {}).get("count", 0),
            "unread_count": counts.get(kind.value, {}).get("unread_count", 0),
        }
        for kind in NotificationKind
    ]
