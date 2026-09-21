from django.db.models import Q

from sova.workflows.models import ActionDependency, ActionTransition, WorkflowAction


class ActionDependencyService:
    """
    Проверки графа зависимостей и переходов действий workflow.

    Зависимости задают непоследовательные шаги: действие можно начать, когда
    выполнены все действия, от которых оно зависит. Цикл (A ждёт B, B ждёт A)
    сделал бы такие действия невыполнимыми, поэтому граф должен оставаться ациклическим.
    """

    def creates_cycle(
        self,
        action: WorkflowAction,
        depends_on_action: WorkflowAction,
        exclude_pk: object | None = None,
    ) -> bool:
        """
        Проверяет, замкнёт ли зависимость `action → depends_on_action` цикл.

        Цикл возникает, если `depends_on_action` уже (прямо или через цепочку
        активных зависимостей) зависит от `action`. `exclude_pk` исключает из
        графа редактируемую зависимость — её старое состояние не должно влиять.
        """
        if action.pk == depends_on_action.pk:
            return True

        edges = self._load_edges(action=action, exclude_pk=exclude_pk)

        visited: set = set()
        pending = [depends_on_action.pk]
        while pending:
            current = pending.pop()
            if current == action.pk:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(edges.get(current, ()))
        return False

    def has_mandatory_dependents(self, action: WorkflowAction) -> bool:
        """Есть ли обязательные действия, ждущие это действие по активной зависимости."""
        return ActionDependency.objects.filter(
            is_active=True,
            depends_on_action=action,
            action__is_optional=False,
        ).exists()

    def waits_for_optional(self, action: WorkflowAction) -> bool:
        """Ждёт ли действие по активной зависимости необязательное действие."""
        return ActionDependency.objects.filter(
            is_active=True,
            action=action,
            depends_on_action__is_optional=True,
        ).exists()

    def has_active_links(self, action: WorkflowAction) -> bool:
        """
        Есть ли у действия активные зависимости или переходы.

        Учитываются обе стороны: действие ждёт или его ждут; его исход ведёт куда-то или переход
        ведёт на него. Границы этапа нарушить можно только через такие связи.
        """
        in_dependencies = ActionDependency.objects.filter(
            Q(action=action) | Q(depends_on_action=action),
            is_active=True,
        ).exists()
        in_transitions = ActionTransition.objects.filter(
            Q(outcome__action=action) | Q(target_action=action),
            is_active=True,
        ).exists()
        return in_dependencies or in_transitions

    def _load_edges(
        self,
        action: WorkflowAction,
        exclude_pk: object | None,
    ) -> dict:
        """Загружает одним запросом активные зависимости workflow: действие → его предусловия."""
        dependencies = ActionDependency.objects.filter(
            is_active=True,
            action__stage__workflow_id=action.stage.workflow_id,
        )
        if exclude_pk is not None:
            dependencies = dependencies.exclude(pk=exclude_pk)

        edges: dict = {}
        for action_id, depends_on_id in dependencies.values_list(
            "action_id",
            "depends_on_action_id",
        ):
            edges.setdefault(action_id, []).append(depends_on_id)
        return edges


action_dependency_service = ActionDependencyService()
