from django.db.models import Exists, OuterRef, Q, QuerySet
from django.http import QueryDict
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.interactions.models import Responsible
from sova.processes.enum import TaskScope
from sova.processes.models import ActionInstance


class ActionInstanceFilter(SearchFilterMixin):
    """
    Фильтр экземпляров действий.

    `scope` делит доступную пользователю выборку на «мои» и «все»: по умолчанию показываются действия,
    где пользователь — ответственный, и действия без ответственного (пул) во взаимодействиях, где он
    действующий КАМ. Границы доступного задаёт роль в СОВА (см. queryset вьюсета),
    поэтому `scope=all` у КАМа не расширяет выдачу за пределы его взаимодействий, а не отвергается.
    """

    stage_instance__ids = UUIDInFilter(
        field_name="stage_instance",
        label=_("Экземпляры этапов"),
        help_text=_("Фильтр по списку ID экземпляров этапов через запятую"),
    )
    workflow_instance__ids = UUIDInFilter(
        field_name="stage_instance__workflow_instance",
        label=_("Процессы"),
        help_text=_("Фильтр по списку ID процессов workflow через запятую; определяется по этапу"),
    )
    interaction__ids = UUIDInFilter(
        field_name="stage_instance__workflow_instance__interaction",
        label=_("Взаимодействия"),
        help_text=_(
            "Фильтр по списку ID взаимодействий через запятую; "
            "берёт действия всех процессов взаимодействия",
        ),
    )
    action__ids = UUIDInFilter(
        field_name="action",
        label=_("Действия"),
        help_text=_("Фильтр по списку ID действий workflow через запятую"),
    )
    responsible__ids = NumberInFilter(
        field_name="responsible",
        label=_("Ответственные"),
        help_text=_("Фильтр по списку ID пользователей-исполнителей через запятую"),
    )
    actual_end__gte = filters.DateFilter(
        field_name="actual_end",
        lookup_expr="date__gte",
        label=_("Завершено с"),
        help_text=_("Начало периода по дате завершения, включительно (ГГГГ-ММ-ДД)"),
    )
    actual_end__lte = filters.DateFilter(
        field_name="actual_end",
        lookup_expr="date__lte",
        label=_("Завершено по"),
        help_text=_("Конец периода по дате завершения, включительно (ГГГГ-ММ-ДД)"),
    )
    scope = filters.ChoiceFilter(
        choices=TaskScope.choices,
        method="filter_scope",
        label=_("Охват"),
        help_text=_(
            "mine (по умолчанию) — действия, где пользователь ответственный, и действия без ответственного "
            "во взаимодействиях, где он действующий КАМ; "
            "all — все действия, доступные ему по роли в СОВА",
        ),
    )

    class Meta:
        model = ActionInstance
        fields = ("status",)

    def __init__(self, data=None, *args, **kwargs) -> None:
        """Подставляет `scope=mine`, если охват не задан: экран «Мои задачи» открывается своими."""
        data = data.copy() if data is not None else QueryDict(mutable=True)
        data.setdefault("scope", TaskScope.MINE)
        super().__init__(data, *args, **kwargs)

    def filter_scope(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Сужает выборку до действий пользователя и пула его взаимодействий; `all` оставляет всё по роли."""
        if value != TaskScope.MINE or self.request is None:
            return queryset
        user = self.request.user
        assigned = Responsible.objects.filter(
            interaction=OuterRef("stage_instance__workflow_instance__interaction"),
            manager=user,
            unassigned_at__isnull=True,
        )
        return queryset.filter(Q(responsible=user) | Q(responsible__isnull=True) & Exists(assigned))
