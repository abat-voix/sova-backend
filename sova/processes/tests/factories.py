import factory
from django.core.files.base import ContentFile

from sova.interactions.tests.factories import InteractionFactory
from sova.processes.models import (
    ActionAttachment,
    ActionInstance,
    ActionResult,
    StageInstance,
    WorkflowInstance,
)
from sova.workflows.tests.factories import (
    ActionOutcomeFactory,
    WorkflowActionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class WorkflowInstanceFactory(factory.django.DjangoModelFactory):
    """Фабрика процесса workflow: B2B-шаблон для взаимодействия с вузом."""

    class Meta:
        model = WorkflowInstance

    status = "running"
    workflow = factory.SubFactory(WorkflowFactory)
    interaction = factory.SubFactory(InteractionFactory)


class StageInstanceFactory(factory.django.DjangoModelFactory):
    """Фабрика экземпляра этапа: этап из того же workflow, что и процесс."""

    class Meta:
        model = StageInstance

    status = "in_progress"
    workflow_instance = factory.SubFactory(WorkflowInstanceFactory)
    stage = factory.SubFactory(
        WorkflowStageFactory,
        workflow=factory.SelfAttribute("..workflow_instance.workflow"),
    )


class ActionInstanceFactory(factory.django.DjangoModelFactory):
    """Фабрика экземпляра действия: действие из того же этапа, что и экземпляр этапа."""

    class Meta:
        model = ActionInstance

    status = "in_progress"
    action_name_snapshot = factory.LazyAttribute(lambda obj: obj.action.name)
    stage_instance = factory.SubFactory(StageInstanceFactory)
    action = factory.SubFactory(
        WorkflowActionFactory,
        stage=factory.SelfAttribute("..stage_instance.stage"),
    )


class ActionResultFactory(factory.django.DjangoModelFactory):
    """Фабрика результата: исход относится к действию экземпляра."""

    class Meta:
        model = ActionResult

    outcome_name_snapshot = factory.LazyAttribute(lambda obj: obj.outcome.name)
    action_instance = factory.SubFactory(ActionInstanceFactory)
    outcome = factory.SubFactory(
        ActionOutcomeFactory,
        action=factory.SelfAttribute("..action_instance.action"),
    )


class ActionAttachmentFactory(factory.django.DjangoModelFactory):
    """Фабрика вложения (тесты должны использовать временный MEDIA_ROOT)."""

    class Meta:
        model = ActionAttachment

    action_instance = factory.SubFactory(ActionInstanceFactory)
    file = factory.LazyAttribute(lambda obj: ContentFile(b"data", name="file.pdf"))
