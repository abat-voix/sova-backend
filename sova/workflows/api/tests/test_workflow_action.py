from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.workflows.enum import WorkflowChangeType
from sova.workflows.models import ActionOutcome, WorkflowAction, WorkflowChange
from sova.workflows.tests.factories import (
    ActionDependencyFactory,
    ActionOutcomeFactory,
    ActionTransitionFactory,
    WorkflowActionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class WorkflowActionApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/workflow-actions/."""

    url_basename = "workflows:workflow-action"
    model = WorkflowAction

    def create_instance(self, **kwargs) -> WorkflowAction:
        """Создаёт действие workflow."""
        return WorkflowActionFactory(**kwargs)

    def get_expected_data(self, instance: WorkflowAction) -> dict:
        """Поля read-представления действия."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "description": instance.description,
            "sort_order": instance.sort_order,
            "default_duration_days": instance.default_duration_days,
            "is_optional": instance.is_optional,
            "starts_by_transition_only": instance.starts_by_transition_only,
            "active": instance.active,
            "stage": {
                "id": str(instance.stage_id),
                "name": instance.stage.name,
                "workflow": str(instance.stage.workflow_id),
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания действия (этап — по id)."""
        return {
            "name": "Позвонить в приёмную",
            "sort_order": 1,
            "default_duration_days": 3,
            "stage": str(WorkflowStageFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления действия."""
        return {"name": "Написать письмо", "default_duration_days": 5}

    def get_search_term(self, instance: WorkflowAction) -> str:
        """Поиск по названию."""
        return instance.name

    def test_add_returns_400_with_duplicate_sort_order(self) -> None:
        """Повтор порядкового номера в этапе возвращает 400."""
        existing = WorkflowActionFactory(sort_order=7)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Дубль порядка",
                "sort_order": 7,
                "stage": str(existing.stage_id),
            },
            format="json",
        )

        # Проверяем, что нарушение unique_stage_action_order отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_stage_and_workflow_ids(self) -> None:
        """Фильтры stage__ids и workflow__ids выбирают действия этапа/workflow."""
        workflow = WorkflowFactory()
        stage = WorkflowStageFactory(workflow=workflow)
        in_stage = WorkflowActionFactory(stage=stage)
        in_workflow = WorkflowActionFactory(
            stage=WorkflowStageFactory(workflow=workflow),
        )
        WorkflowActionFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return sorted(item["id"] for item in response.data["results"])

        # Проверяем фильтр по этапу
        self.assertEqual(ids({"stage__ids": str(stage.pk)}), [str(in_stage.pk)])
        # Проверяем фильтр по workflow через этап
        self.assertEqual(
            ids({"workflow__ids": str(workflow.pk)}),
            sorted([str(in_stage.pk), str(in_workflow.pk)]),
        )

    def patch_action(self, action, **data):
        """Отправляет PATCH действия."""
        return self.client.patch(path=self.detail_url(action), data=data, format="json")

    def test_add_stores_starts_by_transition_only(self) -> None:
        """Признак «запускается только переходом» задаётся при создании."""
        data = {**self.get_post_data(), "starts_by_transition_only": True}

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что признак сохранён и отдан в ответе
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertTrue(response.data["starts_by_transition_only"])

    def test_add_creates_default_outcome(self) -> None:
        """Новое действие получает исход «Выполнено»: без исхода действие нельзя завершить."""
        response = self.client.post(path=self.list_url, data=self.get_post_data(), format="json")

        outcomes = ActionOutcome.objects.filter(action_id=response.data["id"])
        # Проверяем, что исход один и с ожидаемыми названием и правилами
        self.assertEqual(outcomes.count(), 1)
        outcome = outcomes.get()
        self.assertEqual(outcome.code, "done")
        self.assertEqual(outcome.name, "Выполнено")
        self.assertTrue(outcome.active)
        self.assertFalse(outcome.comment_required)
        self.assertFalse(outcome.attachment_required)

    def test_add_records_default_outcome_in_audit(self) -> None:
        """Исход по умолчанию попадает в аудит как созданный текущим пользователем."""
        response = self.client.post(path=self.list_url, data=self.get_post_data(), format="json")

        outcome = ActionOutcome.objects.get(action_id=response.data["id"])
        change = WorkflowChange.objects.get(entity_id=outcome.pk)
        # Проверяем тип изменения, сущность и автора
        self.assertEqual(change.change_type, WorkflowChangeType.CREATED)
        self.assertEqual(change.entity_type, "actionoutcome")
        self.assertEqual(change.created_by_id, self.user.pk)

    def test_add_with_invalid_data_creates_no_outcome(self) -> None:
        """Отклонённый запрос не оставляет исходов."""
        existing = WorkflowActionFactory(sort_order=7)
        outcomes_before = ActionOutcome.objects.count()

        self.client.post(
            path=self.list_url,
            data={"name": "Дубль порядка", "sort_order": 7, "stage": str(existing.stage_id)},
            format="json",
        )

        # Проверяем, что число исходов не изменилось
        self.assertEqual(ActionOutcome.objects.count(), outcomes_before)

    def test_change_returns_400_when_moving_action_with_dependency_to_another_stage(self) -> None:
        """Действие с активной зависимостью нельзя перенести в другой этап: зависимость вышла бы за этап."""
        dependency = ActionDependencyFactory()
        other_stage = WorkflowStageFactory(workflow=dependency.action.stage.workflow)

        response = self.patch_action(dependency.action, stage=str(other_stage.pk))

        # Проверяем, что ошибка привязана к полю stage
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stage", response.data)

    def test_change_returns_400_when_moving_prerequisite_to_another_stage(self) -> None:
        """Действие, от которого зависят другие, тоже нельзя перенести в другой этап."""
        dependency = ActionDependencyFactory()
        other_stage = WorkflowStageFactory(workflow=dependency.action.stage.workflow)

        response = self.patch_action(dependency.depends_on_action, stage=str(other_stage.pk))

        # Проверяем, что перенос отклонён
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stage", response.data)

    def test_change_returns_400_when_moving_action_with_outgoing_transition(self) -> None:
        """Действие, чей исход ведёт на другое действие, нельзя перенести в другой этап."""
        transition = ActionTransitionFactory()
        action = transition.outcome.action
        other_stage = WorkflowStageFactory(workflow=action.stage.workflow)

        response = self.patch_action(action, stage=str(other_stage.pk))

        # Проверяем, что перенос отклонён
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stage", response.data)

    def test_change_returns_400_when_moving_transition_target_to_another_stage(self) -> None:
        """Действие, на которое ведёт переход, нельзя перенести в другой этап."""
        transition = ActionTransitionFactory()
        target = transition.target_action
        other_stage = WorkflowStageFactory(workflow=target.stage.workflow)

        response = self.patch_action(target, stage=str(other_stage.pk))

        # Проверяем, что перенос отклонён
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stage", response.data)

    def test_change_allows_moving_action_with_only_inactive_links(self) -> None:
        """Неактивные зависимость и переход перенос не блокируют."""
        dependency = ActionDependencyFactory(active=False)
        ActionTransitionFactory(
            outcome=ActionOutcomeFactory(action=dependency.action),
            target_action=WorkflowActionFactory(stage=dependency.action.stage),
            active=False,
        )
        other_stage = WorkflowStageFactory(workflow=dependency.action.stage.workflow)

        response = self.patch_action(dependency.action, stage=str(other_stage.pk))

        # Проверяем, что перенос выполнен
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_allows_moving_action_without_links(self) -> None:
        """Действие без связей переносится в другой этап свободно."""
        action = WorkflowActionFactory()
        other_stage = WorkflowStageFactory(workflow=action.stage.workflow)

        response = self.patch_action(action, stage=str(other_stage.pk))

        # Проверяем, что перенос выполнен
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_allows_saving_action_with_links_in_the_same_stage(self) -> None:
        """Правка действия без смены этапа не мешает его связям."""
        dependency = ActionDependencyFactory()

        response = self.patch_action(
            dependency.action,
            stage=str(dependency.action.stage_id),
            name="Новое имя",
        )

        # Проверяем, что правка прошла
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_returns_400_when_making_optional_an_action_with_mandatory_dependents(self) -> None:
        """Нельзя сделать действие необязательным, если от него зависит обязательное."""
        stage = WorkflowStageFactory()
        prerequisite = WorkflowActionFactory(stage=stage, is_optional=False)
        ActionDependencyFactory(
            action=WorkflowActionFactory(stage=stage, is_optional=False),
            depends_on_action=prerequisite,
        )

        response = self.patch_action(prerequisite, is_optional=True)

        # Проверяем, что ошибка привязана к полю is_optional
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_optional", response.data)

    def test_change_allows_making_optional_an_action_with_only_optional_dependents(self) -> None:
        """Необязательное действие может ждать другое необязательное."""
        stage = WorkflowStageFactory()
        prerequisite = WorkflowActionFactory(stage=stage, is_optional=False)
        ActionDependencyFactory(
            action=WorkflowActionFactory(stage=stage, is_optional=True),
            depends_on_action=prerequisite,
        )

        response = self.patch_action(prerequisite, is_optional=True)

        # Проверяем, что изменение прошло
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_returns_400_when_making_mandatory_an_action_that_waits_for_optional(self) -> None:
        """Нельзя сделать действие обязательным, если оно ждёт необязательное."""
        stage = WorkflowStageFactory()
        dependent = WorkflowActionFactory(stage=stage, is_optional=True)
        ActionDependencyFactory(
            action=dependent,
            depends_on_action=WorkflowActionFactory(stage=stage, is_optional=True),
        )

        response = self.patch_action(dependent, is_optional=False)

        # Проверяем, что ошибка привязана к полю is_optional
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_optional", response.data)

    def test_change_allows_making_mandatory_an_action_that_waits_for_mandatory(self) -> None:
        """Обязательное действие может ждать другое обязательное."""
        stage = WorkflowStageFactory()
        dependent = WorkflowActionFactory(stage=stage, is_optional=True)
        ActionDependencyFactory(
            action=dependent,
            depends_on_action=WorkflowActionFactory(stage=stage, is_optional=False),
        )

        response = self.patch_action(dependent, is_optional=False)

        # Проверяем, что изменение прошло
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
