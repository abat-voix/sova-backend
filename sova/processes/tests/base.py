from django.test import TestCase
from rest_framework.test import APITestCase

from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.interactions.tests.factories import InteractionFactory
from sova.processes.enum import ActionInstanceStatus, RollbackMode, StageInstanceContextType
from sova.processes.models import ActionInstance, StageInstance
from sova.processes.services import workflow_engine_service as engine
from sova.workflows.models import ActionOutcome
from sova.workflows.tests.builders import WorkflowBuilder

PRODUCT = StageInstanceContextType.PRODUCT
PROGRAM = StageInstanceContextType.PROGRAM
DIRECTION = StageInstanceContextType.DIRECTION
PENDING = ActionInstanceStatus.PENDING
IN_PROGRESS = ActionInstanceStatus.IN_PROGRESS
COMPLETED = ActionInstanceStatus.COMPLETED


class EngineTestCase(TemporaryMediaMixin, TestCase):
    """Общие помощники тестов движка: запуск процесса и чтение состояния из базы."""

    def setUp(self) -> None:
        """Создаёт пустой B2B-workflow, взаимодействие с вузом и пользователя."""
        self.builder = WorkflowBuilder()
        self.interaction = InteractionFactory()
        self.user = UserFactory()

    def start(self):
        """Запускает процесс для взаимодействия."""
        return engine.start(
            workflow=self.builder.workflow,
            interaction=self.interaction,
            started_by=self.user,
        )

    def context_id(self, context=None):
        """Id контекста этапа: сам контекст (продукт, программа) или взаимодействие целиком."""
        return context.pk if context is not None else self.interaction.pk

    def stage_instance(self, process, stage, context=None) -> StageInstance:
        """Читает из базы экземпляр этапа для контекста."""
        return StageInstance.objects.get(
            workflow_instance=process,
            stage=stage,
            context_id=self.context_id(context),
        )

    def action_instance(self, process, action, context=None) -> ActionInstance:
        """Читает из базы последнее исполнение действия для контекста."""
        return (
            ActionInstance.objects.filter(
                stage_instance__workflow_instance=process,
                stage_instance__context_id=self.context_id(context),
                action=action,
            )
            .order_by("-execution_no")
            .first()
        )

    def stage_status(self, process, stage, context=None) -> str:
        """Статус экземпляра этапа."""
        return self.stage_instance(process, stage, context).status

    def action_status(self, process, action, context=None) -> str:
        """Статус последнего исполнения действия."""
        return self.action_instance(process, action, context).status

    def complete(self, process, action, code="done", comment="", context=None):
        """Завершает последнее исполнение действия с исходом по коду."""
        return engine.complete_action(
            action_instance=self.action_instance(process, action, context),
            outcome=ActionOutcome.objects.get(action=action, code=code),
            comment=comment,
            completed_by=self.user,
        )

    def cancel(self, process, stage, mode=RollbackMode.RESTART, reason="Ошибка", context=None, return_to=None):
        """Отменяет этап и возвращает процесс на предыдущий."""
        return engine.cancel_stage(
            stage_instance=self.stage_instance(process, stage, context),
            mode=mode,
            reason=reason,
            cancelled_by=self.user,
            return_to=return_to,
        )

    def cancel_action(self, process, action, reason="Ошибка", context=None):
        """Откатывает последнее исполнение действия."""
        return engine.cancel_action(
            action_instance=self.action_instance(process, action, context),
            reason=reason,
            cancelled_by=self.user,
        )


class EngineApiTestCase(EngineTestCase, APITestCase):
    """Тесты эндпоинтов движка: те же помощники, а запросы идут от аутентифицированного пользователя."""

    def setUp(self) -> None:
        """Аутентифицирует клиента пользователем, от имени которого движок пишет результаты."""
        super().setUp()
        self.client.force_authenticate(user=self.user)
