from django.utils.translation import gettext_lazy as _

from sova.core.api.filters import NumberInFilter, SearchFilterMixin
from sova.workflows.models import Workflow


class WorkflowFilter(SearchFilterMixin):
    """Фильтр шаблонов workflow."""

    created_by__ids = NumberInFilter(
        field_name="created_by",
        label=_("Авторы"),
        help_text=_("Фильтр по списку ID пользователей-авторов через запятую"),
    )

    class Meta:
        model = Workflow
        fields = (
            "audience",
            "is_base",
            "active",
        )
        exact_search_fields = ["code"]
