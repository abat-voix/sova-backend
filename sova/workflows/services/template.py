from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Model

from sova.workflows.enum import WorkflowChangeType
from sova.workflows.models import (
    ActionDependency,
    ActionOutcome,
    ActionTransition,
    StageTransition,
    Workflow,
    WorkflowAction,
    WorkflowStage,
)
from sova.workflows.schemas import ActionSpec, WorkflowSpec
from sova.workflows.services.audit import workflow_audit_service
from sova.workflows.services.dependency import action_dependency_service
from sova.workflows.services.outcome import action_outcome_service
from sova.workflows.services.stage_transition import stage_transition_service


class WorkflowTemplateError(ValueError):
    """Декларация шаблона противоречива: неизвестное имя, нарушенная граница этапа или цикл."""


class WorkflowTemplateService:
    """
    Сборка готового шаблона workflow из декларации `WorkflowSpec`.

    Нужна там, где шаблон создаётся не руками администратора через API: management-команда,
    заготовка стенда. Правила те же, что в API: этапы и действия нумеруются по порядку
    объявления, графы этапов и зависимостей остаются ациклическими, зависимости и переходы
    не выходят за границу этапа, у каждого действия есть хотя бы один исход.

    Сущности создаются в четыре прохода — этапы, действия, зависимости, переходы, — потому что
    связь может ссылаться на объявленное ниже: исход «Нужны правки» запускает действие, которое
    идёт дальше по списку.

    Вся сборка идёт в одной транзакции: ошибка в декларации не оставляет полусобранный шаблон.
    Созданные сущности копятся в списке и журналируются в конце, поэтому сервис состояния
    не хранит и остаётся синглтоном.
    """

    def create(
        self,
        spec: WorkflowSpec,
        is_base: bool = False,
        created_by: AbstractBaseUser | None = None,
    ) -> Workflow:
        """Создаёт шаблон и его граф. `is_base` задаёт вызывающий: базовый шаблон один на аудиторию."""
        created: list[Model] = []
        with transaction.atomic():
            workflow = Workflow.objects.create(
                code=spec.code,
                name=spec.name,
                audience=spec.audience,
                description=spec.description,
                stale_threshold_days=spec.stale_threshold_days,
                is_base=is_base,
                created_by=created_by,
            )
            created.append(workflow)
            stages = self._create_stages(workflow=workflow, spec=spec, created=created)
            self._link_stages(spec=spec, stages=stages, created=created)
            actions = self._create_actions(spec=spec, stages=stages, created=created)
            self._link_actions(spec=spec, actions=actions, created=created)
            self._record_audit(created=created, created_by=created_by)
            return workflow

    def _create_stages(
        self,
        workflow: Workflow,
        spec: WorkflowSpec,
        created: list[Model],
    ) -> dict[str, WorkflowStage]:
        """Создаёт этапы по порядку объявления: первый — начальный, последний — финальный."""
        stages: dict[str, WorkflowStage] = {}
        last = len(spec.stages)
        for order, stage_spec in enumerate(spec.stages, start=1):
            if stage_spec.name in stages:
                raise WorkflowTemplateError(f"Этап «{stage_spec.name}» объявлен дважды.")
            stage = WorkflowStage.objects.create(
                workflow=workflow,
                name=stage_spec.name,
                type=stage_spec.type,
                description=stage_spec.description,
                sort_order=order,
                is_initial=order == 1,
                is_final=order == last,
                is_optional=stage_spec.is_optional,
            )
            stages[stage_spec.name] = stage
            created.append(stage)
        return stages

    def _link_stages(
        self,
        spec: WorkflowSpec,
        stages: dict[str, WorkflowStage],
        created: list[Model],
    ) -> None:
        """Создаёт связи «этап открывается после закрытия этапов `after`»."""
        for stage_spec in spec.stages:
            target = stages[stage_spec.name]
            for source_name in stage_spec.after:
                source = stages.get(source_name)
                if source is None:
                    raise WorkflowTemplateError(
                        f"Этап «{stage_spec.name}» ссылается на неизвестный этап «{source_name}».",
                    )
                if stage_transition_service.creates_cycle(from_stage=source, to_stage=target):
                    raise WorkflowTemplateError(
                        f"Связь «{source.name}» → «{target.name}» образует цикл.",
                    )
                created.append(StageTransition.objects.create(from_stage=source, to_stage=target))

    def _create_actions(
        self,
        spec: WorkflowSpec,
        stages: dict[str, WorkflowStage],
        created: list[Model],
    ) -> dict[str, WorkflowAction]:
        """Создаёт действия всех этапов с их исходами; нумерация — своя внутри каждого этапа."""
        actions: dict[str, WorkflowAction] = {}
        for stage_spec in spec.stages:
            for order, action_spec in enumerate(stage_spec.actions, start=1):
                if action_spec.name in actions:
                    raise WorkflowTemplateError(f"Действие «{action_spec.name}» объявлено дважды.")
                action = WorkflowAction.objects.create(
                    stage=stages[stage_spec.name],
                    name=action_spec.name,
                    description=action_spec.description,
                    sort_order=order,
                    default_duration_days=action_spec.duration_days,
                    is_optional=action_spec.is_optional,
                    is_trigger_only=action_spec.is_trigger_only,
                )
                actions[action_spec.name] = action
                created.append(action)
                self._create_outcomes(action=action, action_spec=action_spec, created=created)
        return actions

    def _create_outcomes(
        self,
        action: WorkflowAction,
        action_spec: ActionSpec,
        created: list[Model],
    ) -> None:
        """Создаёт исходы действия; без объявленных — исход по умолчанию «Выполнено»."""
        if not action_spec.outcomes:
            created.append(action_outcome_service.create_default(action=action))
            return
        for outcome_spec in action_spec.outcomes:
            created.append(
                ActionOutcome.objects.create(
                    action=action,
                    code=outcome_spec.code,
                    name=outcome_spec.name,
                    is_comment_required=outcome_spec.is_comment_required,
                    is_attachment_required=outcome_spec.is_attachment_required,
                ),
            )

    def _link_actions(
        self,
        spec: WorkflowSpec,
        actions: dict[str, WorkflowAction],
        created: list[Model],
    ) -> None:
        """Создаёт зависимости действий и переходы по исходам."""
        for stage_spec in spec.stages:
            for action_spec in stage_spec.actions:
                action = actions[action_spec.name]
                for name in action_spec.after:
                    self._create_dependency(action=action, name=name, actions=actions, created=created)
                for outcome_spec in action_spec.outcomes:
                    if outcome_spec.starts is None:
                        continue
                    self._create_transition(
                        action=action,
                        code=outcome_spec.code,
                        name=outcome_spec.starts,
                        actions=actions,
                        created=created,
                    )

    def _create_dependency(
        self,
        action: WorkflowAction,
        name: str,
        actions: dict[str, WorkflowAction],
        created: list[Model],
    ) -> None:
        """Создаёт зависимость действия от действия того же этапа."""
        depends_on = self._resolve_action(source=action, name=name, actions=actions)
        if not action.is_optional and depends_on.is_optional:
            raise WorkflowTemplateError(
                f"Действие «{action.name}» обязательное и не может зависеть "
                f"от необязательного «{depends_on.name}».",
            )
        if action_dependency_service.creates_cycle(action=action, depends_on_action=depends_on):
            raise WorkflowTemplateError(
                f"Зависимость «{action.name}» от «{depends_on.name}» образует цикл.",
            )
        created.append(ActionDependency.objects.create(action=action, depends_on_action=depends_on))

    def _create_transition(
        self,
        action: WorkflowAction,
        code: str,
        name: str,
        actions: dict[str, WorkflowAction],
        created: list[Model],
    ) -> None:
        """Создаёт переход: исход `code` действия `action` запускает действие `name`."""
        target = self._resolve_action(source=action, name=name, actions=actions)
        created.append(
            ActionTransition.objects.create(
                outcome=ActionOutcome.objects.get(action=action, code=code),
                target_action=target,
            ),
        )

    def _resolve_action(
        self,
        source: WorkflowAction,
        name: str,
        actions: dict[str, WorkflowAction],
    ) -> WorkflowAction:
        """
        Находит действие по имени из декларации.

        Зависимости и переходы живут внутри одного этапа: порядок этапов задают только связи
        между этапами, поэтому ссылка на действие другого этапа — ошибка декларации.
        """
        target = actions.get(name)
        if target is None:
            raise WorkflowTemplateError(
                f"Действие «{source.name}» ссылается на неизвестное действие «{name}».",
            )
        if target.stage_id != source.stage_id:
            raise WorkflowTemplateError(
                f"Действие «{source.name}» ссылается на «{name}» из другого этапа.",
            )
        return target

    def _record_audit(self, created: list[Model], created_by: AbstractBaseUser | None) -> None:
        """Журналирует созданные сущности так же, как это делает API."""
        for instance in created:
            workflow_audit_service.record(
                instance=instance,
                change_type=WorkflowChangeType.CREATED,
                changed_by=created_by,
            )


workflow_template_service = WorkflowTemplateService()
