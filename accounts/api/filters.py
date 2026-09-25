from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from accounts.models import SystemRole


class UserFilter(filters.FilterSet):
    """Фильтр списка пользователей: активность, команда руководителя, роль."""

    TEAM_MINE = "mine"
    TEAM_FREE = "free"

    is_active = filters.BooleanFilter(
        label=_("Активен"),
        help_text=_("Активность учётной записи; без параметра — только активные"),
    )
    team = filters.ChoiceFilter(
        choices=((TEAM_MINE, _("Моя команда")), (TEAM_FREE, _("Без руководителя"))),
        method="filter_team",
        label=_("Команда"),
        help_text=_("mine — КАМы текущего руководителя, free — пользователи без руководителя"),
    )
    role = filters.MultipleChoiceFilter(
        field_name="system_role__role",
        choices=SystemRole.choices,
        label=_("Роль в системе"),
        help_text=_("Одна или несколько ролей: `?role=kam&role=head`"),
    )
    head = filters.NumberFilter(
        field_name="supervision__head",
        label=_("Руководитель"),
        help_text=_("Id руководителя — его команда"),
    )

    class Meta:
        model = get_user_model()
        fields = ()

    def filter_team(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Своя команда запрашивающего или пользователи без руководителя."""
        if value == self.TEAM_MINE:
            return queryset.filter(supervision__head=self.request.user)
        return queryset.filter(supervision__isnull=True)
