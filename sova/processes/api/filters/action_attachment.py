from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.processes.models import ActionAttachment


class ActionAttachmentFilter(SearchFilterMixin):
    """Фильтр вложений действий."""

    action_instance__ids = UUIDInFilter(
        field_name="action_instance",
        label=_("Экземпляры действий"),
        help_text=_("Фильтр по списку ID экземпляров действий через запятую"),
    )
    uploaded_by__ids = NumberInFilter(
        field_name="uploaded_by",
        label=_("Кто загрузил"),
        help_text=_("Фильтр по списку ID пользователей через запятую"),
    )

    class Meta:
        model = ActionAttachment
        fields = ()
