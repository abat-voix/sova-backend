import factory

from sova.workflows.enum import ActionFeatureCode
from sova.workflows.models import (
    ActionDependency,
    ActionFeature,
    ActionOutcome,
    ActionTransition,
    StageTransition,
    Workflow,
    WorkflowAction,
    WorkflowChange,
    WorkflowStage,
)


class WorkflowFactory(factory.django.DjangoModelFactory):
    """Фабрика шаблона workflow (небазового)."""

    class Meta:
        model = Workflow

    name = factory.Sequence(lambda n: f"Workflow {n}")
    code = factory.Sequence(lambda n: f"workflow-{n}")


class WorkflowStageFactory(factory.django.DjangoModelFactory):
    """Фабрика этапа workflow."""

    class Meta:
        model = WorkflowStage

    name = factory.Sequence(lambda n: f"Этап {n}")
    sort_order = factory.Sequence(lambda n: n)
    workflow = factory.SubFactory(WorkflowFactory)


class StageTransitionFactory(factory.django.DjangoModelFactory):
    """Фабрика связи между этапами: оба этапа — из одного workflow."""

    class Meta:
        model = StageTransition

    from_stage = factory.SubFactory(WorkflowStageFactory)
    to_stage = factory.SubFactory(
        WorkflowStageFactory,
        workflow=factory.SelfAttribute("..from_stage.workflow"),
    )


class WorkflowActionFactory(factory.django.DjangoModelFactory):
    """Фабрика действия workflow."""

    class Meta:
        model = WorkflowAction

    name = factory.Sequence(lambda n: f"Действие {n}")
    sort_order = factory.Sequence(lambda n: n)
    stage = factory.SubFactory(WorkflowStageFactory)


class ActionOutcomeFactory(factory.django.DjangoModelFactory):
    """Фабрика исхода действия."""

    class Meta:
        model = ActionOutcome

    code = factory.Sequence(lambda n: f"outcome-{n}")
    name = factory.Sequence(lambda n: f"Исход {n}")
    action = factory.SubFactory(WorkflowActionFactory)


class ActionFeatureFactory(factory.django.DjangoModelFactory):
    """Фабрика возможности действия."""

    class Meta:
        model = ActionFeature

    code = factory.Iterator(ActionFeatureCode.values)
    sort_order = factory.Sequence(lambda n: n + 1)
    action = factory.SubFactory(WorkflowActionFactory)


class ActionTransitionFactory(factory.django.DjangoModelFactory):
    """Фабрика перехода: целевое действие — из того же workflow, что и исход."""

    class Meta:
        model = ActionTransition

    outcome = factory.SubFactory(ActionOutcomeFactory)
    target_action = factory.SubFactory(
        WorkflowActionFactory,
        stage=factory.SelfAttribute("..outcome.action.stage"),
    )


class ActionDependencyFactory(factory.django.DjangoModelFactory):
    """Фабрика зависимости: оба действия — из одного этапа."""

    class Meta:
        model = ActionDependency

    action = factory.SubFactory(WorkflowActionFactory)
    depends_on_action = factory.SubFactory(
        WorkflowActionFactory,
        stage=factory.SelfAttribute("..action.stage"),
    )


class WorkflowChangeFactory(factory.django.DjangoModelFactory):
    """Фабрика записи аудита изменений workflow."""

    class Meta:
        model = WorkflowChange

    change_type = "created"
    entity_type = "workflowstage"
    entity_id = factory.Faker("uuid4", cast_to=None)
    workflow = factory.SubFactory(WorkflowFactory)
