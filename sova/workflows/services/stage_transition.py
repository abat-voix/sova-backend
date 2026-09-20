from django.db.models import Q

from sova.workflows.models import StageTransition, WorkflowStage


class StageTransitionService:
    """
    Проверки графа связей между этапами workflow.

    Связь `A → B` означает, что этап B открывается после закрытия этапа A. Цикл (A ждёт B, B ждёт A)
    сделал бы такие этапы неоткрываемыми, поэтому граф должен оставаться ациклическим.
    В графе участвуют только активные связи одного workflow.
    """

    def creates_cycle(
        self,
        from_stage: WorkflowStage,
        to_stage: WorkflowStage,
        exclude_pk: object | None = None,
    ) -> bool:
        """
        Проверяет, замкнёт ли связь `from_stage → to_stage` цикл.

        Цикл возникает, если `from_stage` уже достижим из `to_stage` по цепочке активных связей.
        `exclude_pk` исключает из графа редактируемую связь — её старое состояние не должно влиять.
        """
        if from_stage.pk == to_stage.pk:
            return True
        edges = self._load_edges(workflow_id=from_stage.workflow_id, exclude_pk=exclude_pk)
        visited: set = set()
        pending = [to_stage.pk]
        while pending:
            current = pending.pop()
            if current == from_stage.pk:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(edges.get(current, ()))
        return False

    def has_active_links(self, stage: WorkflowStage) -> bool:
        """Есть ли у этапа активные связи: входящие или исходящие."""
        return StageTransition.objects.filter(
            Q(from_stage=stage) | Q(to_stage=stage),
            active=True,
        ).exists()

    def _load_edges(self, workflow_id: object, exclude_pk: object | None) -> dict:
        """Загружает одним запросом активные связи workflow: этап → этапы, которые он открывает."""
        transitions = StageTransition.objects.filter(active=True, from_stage__workflow_id=workflow_id)
        if exclude_pk is not None:
            transitions = transitions.exclude(pk=exclude_pk)
        edges: dict = {}
        for from_id, to_id in transitions.values_list("from_stage_id", "to_stage_id"):
            edges.setdefault(from_id, []).append(to_id)
        return edges


stage_transition_service = StageTransitionService()
