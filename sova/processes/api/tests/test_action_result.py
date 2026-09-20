from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.processes.models import ActionResult
from sova.processes.tests.factories import ActionResultFactory


class ActionResultApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения /api/processes/action-results/: результаты пишет только движок при завершении действия."""

    url_basename = "processes:action-result"
    model = ActionResult
    allow_create = False
    allow_update = False
    allow_delete = False

    def create_instance(self, **kwargs) -> ActionResult:
        """Создаёт результат действия."""
        return ActionResultFactory(**kwargs)

    def get_expected_data(self, instance: ActionResult) -> dict:
        """Поля read-представления результата."""
        return {
            "id": str(instance.pk),
            "action_instance": str(instance.action_instance_id),
            "outcome": {
                "id": str(instance.outcome_id),
                "code": instance.outcome.code,
                "name": instance.outcome.name,
            },
            "outcome_name_snapshot": instance.outcome_name_snapshot,
            "comment": instance.comment,
        }

    def get_post_data(self) -> dict:
        """Создание не поддерживается."""
        return {}

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def test_filters_select_matching_results(self) -> None:
        """Фильтры экземпляра действия, исхода и автора выбирают нужные результаты."""
        author = UserFactory()
        target = ActionResultFactory(created_by=author)
        ActionResultFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return [item["id"] for item in response.data["results"]]

        # Проверяем каждый фильтр
        self.assertEqual(
            ids({"action_instance__ids": str(target.action_instance_id)}),
            [str(target.pk)],
        )
        self.assertEqual(ids({"outcome__ids": str(target.outcome_id)}), [str(target.pk)])
        self.assertEqual(ids({"created_by__ids": str(author.pk)}), [str(target.pk)])
