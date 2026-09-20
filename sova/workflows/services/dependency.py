from sova.workflows.models import ActionDependency, WorkflowAction


class ActionDependencyService:
    """
    Проверки графа зависимостей действий workflow.

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

    def _load_edges(
        self,
        action: WorkflowAction,
        exclude_pk: object | None,
    ) -> dict:
        """Загружает одним запросом активные зависимости workflow: действие → его предусловия."""
        dependencies = ActionDependency.objects.filter(
            active=True,
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
