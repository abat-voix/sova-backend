from collections import defaultdict

from django.db.models import Count
from django.utils import timezone

from sova.interactions.models import InteractionDirection, InteractionProduct, InteractionProgram
from sova.processes.enum import ActionInstanceStatus, StageInstanceContextType, StageInstanceStatus
from sova.processes.models import ActionAttachment, ActionInstance, ActionResult, StageInstance, WorkflowInstance
from sova.processes.services.engine import ProcessSnapshot, workflow_engine_service
from sova.workflows.models import ActionOutcome

# Порядок групп контекстов на доске: направления, программы, продукты
_CONTEXT_ORDER = {
    StageInstanceContextType.DIRECTION: 0,
    StageInstanceContextType.PROGRAM: 1,
    StageInstanceContextType.PRODUCT: 2,
}


class WorkflowBoardService:
    """
    Доска процесса: всё для визуализации пути взаимодействия одним объектом.

    Этапы взаимодействия идут по порядку показа, этапы направлений, программ и продуктов собраны в группы
    по контексту. У каждого этапа в работе перечислены этапы, на которые можно вернуться при отмене; у каждого
    действия в работе — исходы, которые можно выбрать. Число запросов не зависит от числа продуктов и действий:
    всё грузится выборками на весь процесс, а карточки собираются в памяти.
    """

    def build(self, process: WorkflowInstance) -> dict:
        """Собирает доску процесса."""
        snapshot = workflow_engine_service.snapshot(process=process)
        action_cards = self._action_cards(process=process)
        titles = self._context_titles(process=process)
        interaction_stages: list[dict] = []
        groups: dict = {}
        for item in sorted(snapshot.instances, key=lambda entry: entry.stage.sort_order):
            if item.stage_id not in snapshot.graph.stages or item.context_id not in snapshot.live[item.context_type]:
                continue
            card = self._stage_card(item=item, snapshot=snapshot, action_cards=action_cards)
            if item.context_type == StageInstanceContextType.INTERACTION:
                interaction_stages.append(card)
                continue
            title, parent_id = titles[item.context_type][item.context_id]
            group = groups.setdefault(
                (item.context_type, item.context_id),
                {
                    "context_type": item.context_type,
                    "context_id": item.context_id,
                    "title": title,
                    "parent_id": parent_id,
                    "stages": [],
                },
            )
            group["stages"].append(card)
        return {
            "id": process.pk,
            "status": process.status,
            "started_at": process.started_at,
            "completed_at": process.completed_at,
            "workflow": process.workflow,
            "interaction": process.interaction,
            "interaction_stages": interaction_stages,
            "context_groups": sorted(
                groups.values(),
                key=lambda group: (_CONTEXT_ORDER[group["context_type"]], group["title"]),
            ),
        }

    def _stage_card(self, item: StageInstance, snapshot: ProcessSnapshot, action_cards: dict) -> dict:
        """Карточка этапа: статус, время, варианты возврата и действия."""
        options = []
        if item.status == StageInstanceStatus.IN_PROGRESS:
            options = [
                {"id": option.pk, "stage_name": option.stage.name}
                for option in workflow_engine_service.return_options(snapshot=snapshot, stage_instance=item)
            ]
        return {
            "id": item.pk,
            "stage": {"id": item.stage_id, "name": item.stage.name},
            "status": item.status,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
            "return_options": options,
            "actions": action_cards.get(item.pk, []),
        }

    def _action_cards(self, process: WorkflowInstance) -> dict:
        """Карточки действий процесса, сгруппированные по экземплярам этапов; на карточке — последнее исполнение."""
        latest: dict = {}
        instances = (
            ActionInstance.objects.filter(stage_instance__workflow_instance=process)
            .select_related("action", "responsible")
            .order_by("stage_instance_id", "action_id", "execution_no")
        )
        for instance in instances:
            latest[(instance.stage_instance_id, instance.action_id)] = instance
        instance_ids = [instance.pk for instance in latest.values()]
        results = {
            result.action_instance_id: result
            for result in ActionResult.objects.filter(action_instance_id__in=instance_ids).select_related("created_by")
        }
        attachments = dict(
            ActionAttachment.objects.filter(action_instance_id__in=instance_ids)
            .order_by()
            .values_list("action_instance_id")
            .annotate(total=Count("id")),
        )
        working_actions = {
            instance.action_id for instance in latest.values() if instance.status == ActionInstanceStatus.IN_PROGRESS
        }
        outcomes: dict = defaultdict(list)
        for outcome in ActionOutcome.objects.filter(action_id__in=working_actions, active=True).order_by("code"):
            outcomes[outcome.action_id].append(outcome)
        now = timezone.now()
        cards: dict = defaultdict(list)
        for instance in sorted(latest.values(), key=lambda entry: entry.action.sort_order):
            cards[instance.stage_instance_id].append(
                self._action_card(
                    instance=instance,
                    result=results.get(instance.pk),
                    attachments_count=attachments.get(instance.pk, 0),
                    outcomes=outcomes.get(instance.action_id, []),
                    now=now,
                ),
            )
        return cards

    def _action_card(
        self,
        instance: ActionInstance,
        result: ActionResult | None,
        attachments_count: int,
        outcomes: list[ActionOutcome],
        now,
    ) -> dict:
        """Карточка действия: последнее исполнение, результат, вложения и исходы, которые можно выбрать."""
        action = instance.action
        in_progress = instance.status == ActionInstanceStatus.IN_PROGRESS
        return {
            "id": instance.pk,
            "action": {"id": action.pk, "name": action.name},
            "name": instance.action_name_snapshot,
            "status": instance.status,
            "is_optional": action.is_optional,
            "starts_by_transition_only": action.starts_by_transition_only,
            "is_triggered": instance.triggered_at is not None,
            "execution_no": instance.execution_no,
            "planned_start": instance.planned_start,
            "planned_end": instance.planned_end,
            "actual_start": instance.actual_start,
            "actual_end": instance.actual_end,
            "is_overdue": in_progress and instance.planned_end is not None and instance.planned_end < now,
            "responsible": instance.responsible,
            "result": (
                {
                    "outcome_name": result.outcome_name_snapshot,
                    "comment": result.comment,
                    "created_at": result.created_at,
                    "created_by": result.created_by,
                }
                if result is not None
                else None
            ),
            "attachments_count": attachments_count,
            "available_outcomes": [
                {
                    "id": outcome.pk,
                    "code": outcome.code,
                    "name": outcome.name,
                    "comment_required": outcome.comment_required,
                    "attachment_required": outcome.attachment_required,
                }
                for outcome in outcomes
            ]
            if in_progress
            else [],
        }

    def _context_titles(self, process: WorkflowInstance) -> dict:
        """Названия контекстов и родитель продукта: тип контекста → id → (название, id программы взаимодействия)."""
        interaction = process.interaction
        titles: dict = {
            StageInstanceContextType.DIRECTION: {
                item.pk: (item.direction.name, None)
                for item in InteractionDirection.objects.filter(interaction=interaction).select_related("direction")
            },
            StageInstanceContextType.PROGRAM: {
                item.pk: (item.program.name, None)
                for item in InteractionProgram.objects.filter(interaction=interaction).select_related("program")
            },
            StageInstanceContextType.PRODUCT: {
                item.pk: (item.product.name, item.interaction_program_id)
                for item in InteractionProduct.objects.filter(interaction=interaction).select_related("product")
            },
        }
        return titles


workflow_board_service = WorkflowBoardService()
