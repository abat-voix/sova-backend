from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.workflows.models import ActionTransition
from sova.workflows.tests.factories import (
    ActionOutcomeFactory,
    ActionTransitionFactory,
    WorkflowActionFactory,
    WorkflowStageFactory,
)


class ActionTransitionApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/action-transitions/."""

    url_basename = "workflows:action-transition"
    model = ActionTransition

    def create_instance(self, **kwargs) -> ActionTransition:
        """Создаёт переход."""
        return ActionTransitionFactory(**kwargs)

    def get_expected_data(self, instance: ActionTransition) -> dict:
        """Поля read-представления перехода."""
        return {
            "id": str(instance.pk),
            "is_active": instance.is_active,
            "outcome": {
                "id": str(instance.outcome_id),
                "code": instance.outcome.code,
                "name": instance.outcome.name,
            },
            "target_action": {
                "id": str(instance.target_action_id),
                "name": instance.target_action.name,
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания перехода: исход и цель из одного workflow."""
        outcome = ActionOutcomeFactory()
        target = WorkflowActionFactory(stage=outcome.action.stage)
        return {"outcome": str(outcome.pk), "target_action": str(target.pk)}

    def get_change_data(self) -> dict:
        """Данные обновления перехода."""
        return {"is_active": False}

    def test_add_returns_400_with_target_from_another_workflow(self) -> None:
        """Целевое действие из другого workflow отклоняется."""
        outcome = ActionOutcomeFactory()
        foreign_target = WorkflowActionFactory()

        response = self.client.post(
            path=self.list_url,
            data={
                "outcome": str(outcome.pk),
                "target_action": str(foreign_target.pk),
            },
            format="json",
        )

        # Проверяем, что ошибка привязана к целевому действию
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_action", response.data)

    def test_add_returns_400_with_target_from_another_stage(self) -> None:
        """Целевое действие из другого этапа того же workflow отклоняется: ветвление по этапам запрещено."""
        outcome = ActionOutcomeFactory()
        other_stage = WorkflowStageFactory(workflow=outcome.action.stage.workflow)
        target = WorkflowActionFactory(stage=other_stage)

        response = self.client.post(
            path=self.list_url,
            data={"outcome": str(outcome.pk), "target_action": str(target.pk)},
            format="json",
        )

        # Проверяем, что ошибка привязана к целевому действию
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_action", response.data)

    def test_add_allows_transition_to_the_same_action(self) -> None:
        """Исход может вести на своё же действие — так выражается повтор."""
        outcome = ActionOutcomeFactory()

        response = self.client.post(
            path=self.list_url,
            data={"outcome": str(outcome.pk), "target_action": str(outcome.action_id)},
            format="json",
        )

        # Проверяем, что переход создан
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_change_returns_400_when_target_switched_to_another_stage(self) -> None:
        """PATCH, переводящий цель в другой этап того же workflow, возвращает 400."""
        instance = ActionTransitionFactory()
        other_stage = WorkflowStageFactory(workflow=instance.outcome.action.stage.workflow)

        response = self.client.patch(
            path=self.detail_url(instance),
            data={"target_action": str(WorkflowActionFactory(stage=other_stage).pk)},
            format="json",
        )

        # Проверяем, что при PATCH сравнивается этап сохранённого исхода
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_action", response.data)

    def test_add_returns_400_when_outcome_already_has_transition(self) -> None:
        """Второй переход от того же исхода возвращает 400 (OneToOne)."""
        existing = ActionTransitionFactory()

        response = self.client.post(
            path=self.list_url,
            data={
                "outcome": str(existing.outcome_id),
                "target_action": str(existing.target_action_id),
            },
            format="json",
        )

        # Проверяем, что уникальность исхода ловится валидацией
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("outcome", response.data)

    def test_change_returns_400_when_target_switched_to_foreign_workflow(self) -> None:
        """PATCH, переводящий цель в другой workflow, возвращает 400."""
        instance = ActionTransitionFactory()

        response = self.client.patch(
            path=self.detail_url(instance),
            data={"target_action": str(WorkflowActionFactory().pk)},
            format="json",
        )

        # Проверяем, что при PATCH сравнивается с сохранённым исходом
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_workflow_and_target_action_ids(self) -> None:
        """Фильтры workflow__ids и target_action__ids выбирают нужные переходы."""
        target = ActionTransitionFactory()
        ActionTransitionFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return [item["id"] for item in response.data["results"]]

        # Проверяем фильтр по workflow через исход → действие → этап
        self.assertEqual(
            ids({"workflow__ids": str(target.outcome.action.stage.workflow_id)}),
            [str(target.pk)],
        )
        # Проверяем фильтр по целевому действию
        self.assertEqual(
            ids({"target_action__ids": str(target.target_action_id)}),
            [str(target.pk)],
        )
