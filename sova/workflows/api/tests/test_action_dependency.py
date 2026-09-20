from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.workflows.models import ActionDependency
from sova.workflows.tests.factories import (
    ActionDependencyFactory,
    WorkflowActionFactory,
    WorkflowStageFactory,
)


class ActionDependencyApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/action-dependencies/."""

    url_basename = "workflows:action-dependency"
    model = ActionDependency

    def create_instance(self, **kwargs) -> ActionDependency:
        """Создаёт зависимость."""
        return ActionDependencyFactory(**kwargs)

    def get_expected_data(self, instance: ActionDependency) -> dict:
        """Поля read-представления зависимости."""
        return {
            "id": str(instance.pk),
            "active": instance.active,
            "action": {"id": str(instance.action_id), "name": instance.action.name},
            "depends_on_action": {
                "id": str(instance.depends_on_action_id),
                "name": instance.depends_on_action.name,
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания зависимости: оба действия из одного workflow."""
        action = WorkflowActionFactory()
        other = WorkflowActionFactory(stage=action.stage)
        return {"action": str(action.pk), "depends_on_action": str(other.pk)}

    def get_change_data(self) -> dict:
        """Данные обновления зависимости."""
        return {"active": False}

    def post_dependency(self, action, depends_on):
        """Отправляет запрос на создание зависимости action → depends_on."""
        return self.client.post(
            path=self.list_url,
            data={"action": str(action.pk), "depends_on_action": str(depends_on.pk)},
            format="json",
        )

    def test_add_returns_400_for_self_reference(self) -> None:
        """Зависимость действия от самого себя возвращает 400."""
        action = WorkflowActionFactory()

        response = self.post_dependency(action=action, depends_on=action)

        # Проверяем, что CheckConstraint не доходит до БД
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_for_actions_from_different_workflows(self) -> None:
        """Зависимость между действиями разных workflow отклоняется."""
        response = self.post_dependency(
            action=WorkflowActionFactory(),
            depends_on=WorkflowActionFactory(),
        )

        # Проверяем, что граф зависимостей не выходит за пределы workflow
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_for_direct_cycle(self) -> None:
        """Обратная зависимость (A→B при существующей B→A) образует цикл."""
        existing = ActionDependencyFactory()

        response = self.post_dependency(
            action=existing.depends_on_action,
            depends_on=existing.action,
        )

        # Проверяем, что цикл отклонён
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_for_transitive_cycle(self) -> None:
        """Зависимость, замыкающая цепочку A→B→C→A, возвращает 400."""
        stage = WorkflowStageFactory()
        a, b, c = WorkflowActionFactory.create_batch(size=3, stage=stage)
        ActionDependencyFactory(action=a, depends_on_action=b)
        ActionDependencyFactory(action=b, depends_on_action=c)

        response = self.post_dependency(action=c, depends_on=a)

        # Проверяем, что цикл найден через промежуточное действие
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_allows_diamond_without_cycle(self) -> None:
        """Ромб зависимостей A→B, A→C, B→D, C→D циклом не считается."""
        stage = WorkflowStageFactory()
        a, b, c, d = WorkflowActionFactory.create_batch(size=4, stage=stage)
        ActionDependencyFactory(action=a, depends_on_action=b)
        ActionDependencyFactory(action=a, depends_on_action=c)
        ActionDependencyFactory(action=b, depends_on_action=d)

        response = self.post_dependency(action=c, depends_on=d)

        # Проверяем, что общий предок не воспринимается как цикл
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_add_ignores_inactive_dependencies_when_looking_for_cycle(self) -> None:
        """Неактивная обратная зависимость цикл не образует."""
        existing = ActionDependencyFactory(active=False)

        response = self.post_dependency(
            action=existing.depends_on_action,
            depends_on=existing.action,
        )

        # Проверяем, что учитываются только активные зависимости
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_change_returns_400_when_reactivating_creates_cycle(self) -> None:
        """Включение зависимости, замыкающей цикл, возвращает 400."""
        first = ActionDependencyFactory()
        reverse = ActionDependencyFactory(
            action=first.depends_on_action,
            depends_on_action=first.action,
            active=False,
        )

        response = self.client.patch(
            path=self.detail_url(reverse),
            data={"active": True},
            format="json",
        )

        # Проверяем, что цикл ловится и при реактивации
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_with_duplicate_dependency(self) -> None:
        """Повтор пары (действие, зависимость) возвращает 400."""
        existing = ActionDependencyFactory()

        response = self.post_dependency(
            action=existing.action,
            depends_on=existing.depends_on_action,
        )

        # Проверяем, что нарушение unique_action_dependency отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_action_and_depends_on_action_ids(self) -> None:
        """Фильтры action__ids и depends_on_action__ids выбирают нужные зависимости."""
        target = ActionDependencyFactory()
        ActionDependencyFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return [item["id"] for item in response.data["results"]]

        # Проверяем фильтр по зависимому действию
        self.assertEqual(ids({"action__ids": str(target.action_id)}), [str(target.pk)])
        # Проверяем фильтр по действию-предусловию
        self.assertEqual(
            ids({"depends_on_action__ids": str(target.depends_on_action_id)}),
            [str(target.pk)],
        )
