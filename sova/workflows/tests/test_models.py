from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from sova.processes.enum import StageInstanceContextType
from sova.workflows.models import StageTransition, WorkflowStage
from sova.workflows.tests.factories import (
    StageTransitionFactory,
    WorkflowActionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class WorkflowStageTypeTest(TestCase):
    """Тесты типа этапа: к чему относится этап — взаимодействию, направлению, программе или продукту."""

    def test_default_type_is_whole_interaction(self) -> None:
        """По умолчанию этап относится ко всему взаимодействию."""
        stage = WorkflowStageFactory()

        # Проверяем значение по умолчанию
        self.assertEqual(stage.type, StageInstanceContextType.INTERACTION)

    def test_type_uses_context_type_values(self) -> None:
        """Допустимые типы этапа совпадают с типами контекста экземпляра этапа (StageInstance.context_type)."""
        # Проверяем, что одно перечисление описывает и этап, и его экземпляры
        self.assertEqual(
            WorkflowStage._meta.get_field("type").choices,
            StageInstanceContextType.choices,
        )

    def test_type_is_required_to_be_one_of_fixed_values(self) -> None:
        """Произвольная строка в качестве типа этапа не проходит валидацию модели."""
        stage = WorkflowStageFactory.build(type="Продукт")

        # Проверяем ошибку по полю type
        with self.assertRaises(ValidationError) as raised:
            stage.clean_fields(exclude=["workflow"])
        self.assertIn("type", raised.exception.message_dict)

    def test_blank_type_is_rejected(self) -> None:
        """Пустой тип этапа недопустим: движок должен знать, к чему относится этап."""
        stage = WorkflowStageFactory.build(type="")

        # Проверяем ошибку по полю type
        with self.assertRaises(ValidationError) as raised:
            stage.clean_fields(exclude=["workflow"])
        self.assertIn("type", raised.exception.message_dict)


class WorkflowActionStartModeTest(TestCase):
    """Тесты признака «запускается только переходом»: такое действие не стартует вместе с этапом."""

    def test_action_starts_with_its_stage_by_default(self) -> None:
        """По умолчанию действие доступно сразу при открытии этапа."""
        action = WorkflowActionFactory()
        # Проверяем значение по умолчанию
        self.assertFalse(action.starts_by_transition_only)

    def test_action_can_be_marked_as_started_only_by_transition(self) -> None:
        """Признак «только по переходу» сохраняется в базе."""
        action = WorkflowActionFactory(starts_by_transition_only=True)

        action.refresh_from_db()

        # Проверяем, что признак не потерялся после перечитывания
        self.assertTrue(action.starts_by_transition_only)


class StageTransitionTest(TestCase):
    """Тесты связи между этапами: этап-цель открывается после закрытия этапа-источника."""

    def test_transition_is_active_by_default(self) -> None:
        """Новая связь между этапами действует."""
        transition = StageTransitionFactory()
        # Проверяем значение по умолчанию
        self.assertTrue(transition.active)

    def test_clean_accepts_stages_of_one_workflow(self) -> None:
        """Связь между этапами одного workflow проходит проверку модели."""
        transition = StageTransitionFactory()
        # Проверяем, что исключения нет
        transition.clean()

    def test_clean_rejects_stages_of_different_workflows(self) -> None:
        """Связь между этапами разных workflow не проходит проверку модели."""
        transition = StageTransition(
            from_stage=WorkflowStageFactory(),
            to_stage=WorkflowStageFactory(),
        )

        # Проверяем ошибку по полю to_stage
        with self.assertRaises(ValidationError) as raised:
            transition.clean()
        self.assertIn("to_stage", raised.exception.message_dict)

    def test_transition_between_same_stages_cannot_be_created_twice(self) -> None:
        """Пара «источник → цель» уникальна."""
        existing = StageTransitionFactory()

        # Проверяем, что база отвергает дубликат
        with self.assertRaises(IntegrityError), transaction.atomic():
            StageTransition.objects.create(
                from_stage=existing.from_stage,
                to_stage=existing.to_stage,
            )

    def test_transition_from_stage_to_itself_is_rejected(self) -> None:
        """Этап не может вести сам на себя."""
        stage = WorkflowStageFactory()

        # Проверяем, что база отвергает самопереход
        with self.assertRaises(IntegrityError), transaction.atomic():
            StageTransition.objects.create(from_stage=stage, to_stage=stage)

    def test_stage_exposes_outgoing_and_incoming_transitions(self) -> None:
        """Из этапа доступны исходящие связи, из цели — входящие."""
        transition = StageTransitionFactory()

        # Проверяем обратные связи с обеих сторон
        self.assertEqual(list(transition.from_stage.stage_transitions_as_from_stage.all()), [transition])
        self.assertEqual(list(transition.to_stage.stage_transitions_as_to_stage.all()), [transition])

    def test_deleting_a_stage_deletes_its_transitions(self) -> None:
        """Удаление этапа убирает связи, в которых он участвует."""
        transition = StageTransitionFactory()

        transition.to_stage.delete()

        # Проверяем, что связь исчезла вместе с этапом
        self.assertFalse(StageTransition.objects.filter(pk=transition.pk).exists())

    def test_clean_rejects_interaction_stage_after_product_stage(self) -> None:
        """Этап взаимодействия не может идти после этапа продукта."""
        workflow = WorkflowFactory()
        transition = StageTransition(
            from_stage=WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.IT_PRODUCT),
            to_stage=WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.INTERACTION),
        )

        # Проверяем ошибку по полю to_stage
        with self.assertRaises(ValidationError) as raised:
            transition.clean()
        self.assertIn("to_stage", raised.exception.message_dict)

    def test_clean_accepts_allowed_combinations_of_stage_types(self) -> None:
        """Допустимы переходы: взаимодействие → любой, а также между этапами одного контекстного типа."""
        workflow = WorkflowFactory()
        allowed = (
            (StageInstanceContextType.INTERACTION, StageInstanceContextType.INTERACTION),
            (StageInstanceContextType.INTERACTION, StageInstanceContextType.IT_PRODUCT),
            (StageInstanceContextType.INTERACTION, StageInstanceContextType.IT_PROGRAM),
            (StageInstanceContextType.IT_PRODUCT, StageInstanceContextType.IT_PRODUCT),
        )
        for source_type, target_type in allowed:
            with self.subTest(source=source_type, target=target_type):
                transition = StageTransition(
                    from_stage=WorkflowStageFactory(workflow=workflow, type=source_type),
                    to_stage=WorkflowStageFactory(workflow=workflow, type=target_type),
                )
                # Проверяем, что исключения нет
                transition.clean()
