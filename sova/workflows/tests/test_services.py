from django.test import TestCase

from sova.workflows.models import ActionOutcome
from sova.workflows.services import action_outcome_service, stage_transition_service
from sova.workflows.tests.factories import (
    ActionOutcomeFactory,
    StageTransitionFactory,
    WorkflowActionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class ActionOutcomeServiceTest(TestCase):
    """Тесты исхода по умолчанию: без исхода действие нельзя завершить."""

    def test_create_default_adds_done_outcome(self) -> None:
        """Действию добавляется исход «Выполнено» без обязательных комментария и вложения."""
        action = WorkflowActionFactory()

        outcome = action_outcome_service.create_default(action=action)

        # Проверяем поля исхода
        self.assertEqual(outcome.action, action)
        self.assertEqual(outcome.code, "done")
        self.assertEqual(outcome.name, "Выполнено")
        self.assertFalse(outcome.is_comment_required)
        self.assertFalse(outcome.is_attachment_required)

    def test_create_default_is_idempotent(self) -> None:
        """Повторный вызов не создаёт второй исход."""
        action = WorkflowActionFactory()

        first = action_outcome_service.create_default(action=action)
        second = action_outcome_service.create_default(action=action)

        # Проверяем, что вернулся тот же исход и он один
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ActionOutcome.objects.filter(action=action).count(), 1)

    def test_create_default_keeps_customised_outcome(self) -> None:
        """Настроенный администратором исход с кодом done не перезаписывается."""
        action = WorkflowActionFactory()
        custom = ActionOutcomeFactory(action=action, code="done", name="Сделано", is_comment_required=True)

        outcome = action_outcome_service.create_default(action=action)

        # Проверяем, что правила остались прежними
        self.assertEqual(outcome.pk, custom.pk)
        outcome.refresh_from_db()
        self.assertEqual(outcome.name, "Сделано")
        self.assertTrue(outcome.is_comment_required)


class StageTransitionServiceTest(TestCase):
    """Тесты проверок графа связей между этапами."""

    def setUp(self) -> None:
        """Создаёт workflow с тремя этапами A, B, C."""
        self.workflow = WorkflowFactory()
        self.a, self.b, self.c = WorkflowStageFactory.create_batch(size=3, workflow=self.workflow)

    def test_creates_cycle_for_reverse_transition(self) -> None:
        """Обратная связь к существующей замыкает цикл."""
        StageTransitionFactory(from_stage=self.a, to_stage=self.b)

        # Проверяем, что B → A замыкает цикл
        self.assertTrue(stage_transition_service.creates_cycle(from_stage=self.b, to_stage=self.a))

    def test_creates_cycle_through_chain(self) -> None:
        """Цикл находится через цепочку связей."""
        StageTransitionFactory(from_stage=self.a, to_stage=self.b)
        StageTransitionFactory(from_stage=self.b, to_stage=self.c)

        # Проверяем, что C → A замыкает цепочку A → B → C
        self.assertTrue(stage_transition_service.creates_cycle(from_stage=self.c, to_stage=self.a))

    def test_creates_cycle_for_self_reference(self) -> None:
        """Связь этапа с самим собой — цикл."""
        # Проверяем самосвязь
        self.assertTrue(stage_transition_service.creates_cycle(from_stage=self.a, to_stage=self.a))

    def test_no_cycle_for_forward_transition(self) -> None:
        """Связь вперёд по цепочке цикла не образует."""
        StageTransitionFactory(from_stage=self.a, to_stage=self.b)

        # Проверяем, что B → C безопасна
        self.assertFalse(stage_transition_service.creates_cycle(from_stage=self.b, to_stage=self.c))

    def test_inactive_transitions_are_ignored(self) -> None:
        """Неактивные связи в графе не участвуют."""
        StageTransitionFactory(from_stage=self.a, to_stage=self.b, is_active=False)

        # Проверяем, что B → A циклом не считается
        self.assertFalse(stage_transition_service.creates_cycle(from_stage=self.b, to_stage=self.a))

    def test_other_workflows_are_ignored(self) -> None:
        """Связи другого workflow граф этого workflow не меняют."""
        other = WorkflowFactory()
        x, y = WorkflowStageFactory.create_batch(size=2, workflow=other)
        StageTransitionFactory(from_stage=x, to_stage=y)

        # Проверяем, что независимый граф не влияет на результат
        self.assertFalse(stage_transition_service.creates_cycle(from_stage=self.a, to_stage=self.b))

    def test_excluded_transition_does_not_form_a_cycle(self) -> None:
        """Редактируемая связь исключается из графа: её старое состояние не учитывается."""
        existing = StageTransitionFactory(from_stage=self.a, to_stage=self.b)

        # Проверяем, что без исключения B → A образует цикл, а с исключением — нет
        self.assertTrue(stage_transition_service.creates_cycle(from_stage=self.b, to_stage=self.a))
        self.assertFalse(
            stage_transition_service.creates_cycle(
                from_stage=self.b,
                to_stage=self.a,
                exclude_pk=existing.pk,
            ),
        )

    def test_has_active_links_for_source_and_target(self) -> None:
        """Активная связь есть и у источника, и у цели; у постороннего этапа её нет."""
        StageTransitionFactory(from_stage=self.a, to_stage=self.b)

        # Проверяем обе стороны связи и посторонний этап
        self.assertTrue(stage_transition_service.has_active_links(stage=self.a))
        self.assertTrue(stage_transition_service.has_active_links(stage=self.b))
        self.assertFalse(stage_transition_service.has_active_links(stage=self.c))

    def test_has_active_links_ignores_inactive_transitions(self) -> None:
        """Неактивная связь не считается."""
        StageTransitionFactory(from_stage=self.a, to_stage=self.b, is_active=False)

        # Проверяем, что связей нет
        self.assertFalse(stage_transition_service.has_active_links(stage=self.a))
