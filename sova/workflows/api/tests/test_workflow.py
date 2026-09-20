from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import InteractionFactory
from sova.processes.models import WorkflowInstance
from sova.workflows.enum import Audience
from sova.workflows.models import Workflow
from sova.workflows.tests.factories import WorkflowFactory, WorkflowStageFactory


class WorkflowApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/workflows/."""

    url_basename = "workflows:workflow"
    model = Workflow

    def create_instance(self, **kwargs) -> Workflow:
        """Создаёт шаблон workflow."""
        return WorkflowFactory(**kwargs)

    def get_expected_data(self, instance: Workflow) -> dict:
        """Поля read-представления workflow."""
        creator = instance.created_by
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "code": instance.code,
            "audience": instance.audience,
            "description": instance.description,
            "stale_threshold_days": instance.stale_threshold_days,
            "is_base": instance.is_base,
            "active": instance.active,
            "created_by": (
                {
                    "id": creator.pk,
                    "email": creator.email,
                    "full_name": creator.get_full_name(),
                }
                if creator
                else None
            ),
            "stages_count": instance.workflow_stages.count(),
        }

    def get_post_data(self) -> dict:
        """Данные создания workflow."""
        return {
            "name": "Процесс для школ",
            "code": "schools",
            "audience": Audience.B2C,
            "stale_threshold_days": 30,
        }

    def get_change_data(self) -> dict:
        """Данные обновления workflow."""
        return {"name": "Новое имя", "description": "Описание"}

    def get_search_term(self, instance: Workflow) -> str:
        """Поиск по названию."""
        return instance.name

    def test_add_sets_created_by(self) -> None:
        """Создание проставляет автора из запроса."""
        response = self.client.post(
            path=self.list_url,
            data=self.get_post_data(),
            format="json",
        )

        # Проверяем автора
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["created_by"]["id"], self.user.pk)

    def test_add_returns_400_with_duplicate_code(self) -> None:
        """Повтор кода workflow возвращает 400."""
        WorkflowFactory(code="dup")

        response = self.client.post(
            path=self.list_url,
            data={"name": "Дубль", "code": "dup"},
            format="json",
        )

        # Проверяем, что ошибка привязана к полю code
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_list_counts_stages(self) -> None:
        """stages_count равен числу этапов workflow."""
        workflow = WorkflowFactory()
        WorkflowStageFactory.create_batch(size=3, workflow=workflow)

        response = self.client.get(path=self.list_url)

        # Проверяем счётчик этапов
        self.assertEqual(response.data["results"][0]["stages_count"], 3)

    def test_add_returns_stages_count_of_new_workflow(self) -> None:
        """Ответ на создание содержит аннотированный stages_count."""
        response = self.client.post(
            path=self.list_url,
            data=self.get_post_data(),
            format="json",
        )

        # Проверяем, что аннотация доступна сразу после создания
        self.assertEqual(response.data["stages_count"], 0)

    def test_add_base_returns_400_when_audience_already_has_base(self) -> None:
        """Второй базовый workflow для аудитории отклоняется с 400."""
        WorkflowFactory(is_base=True, audience=Audience.B2B)

        response = self.client.post(
            path=self.list_url,
            data={"name": "Ещё базовый", "code": "base-2", "is_base": True},
            format="json",
        )

        # Проверяем, что ограничение БД не доходит до 500/409
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_base", response.data)

    def test_add_base_for_another_audience_creates_workflow(self) -> None:
        """Базовые workflow разных аудиторий сосуществуют."""
        WorkflowFactory(is_base=True, audience=Audience.B2B)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Базовый B2C",
                "code": "base-b2c",
                "is_base": True,
                "audience": Audience.B2C,
            },
            format="json",
        )

        # Проверяем, что создан второй базовый — для другой аудитории
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_change_base_workflow_keeps_it_base(self) -> None:
        """Обновление самого базового workflow не конфликтует с его же флагом."""
        base = WorkflowFactory(is_base=True)

        response = self.client.patch(
            path=self.detail_url(base),
            data={"name": "Переименован", "is_base": True},
            format="json",
        )

        # Проверяем, что собственный флаг is_base не считается конфликтом
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_audience_of_base_returns_400_when_target_has_base(self) -> None:
        """Смена аудитории базового workflow на занятую отклоняется."""
        WorkflowFactory(is_base=True, audience=Audience.B2C)
        base = WorkflowFactory(is_base=True, audience=Audience.B2B)

        response = self.client.patch(
            path=self.detail_url(base),
            data={"audience": Audience.B2C},
            format="json",
        )

        # Проверяем, что при PATCH учитывается сохранённый is_base
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_returns_409_when_workflow_has_instances(self) -> None:
        """Удаление workflow с запущенными процессами возвращает 409 с кодом protected."""
        workflow = WorkflowFactory()
        WorkflowInstance.objects.create(
            workflow=workflow,
            interaction=InteractionFactory(),
            status="running",
        )

        response = self.client.delete(path=self.detail_url(workflow))

        # Проверяем, что защита PROTECT превращается в 409, а не 500
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "protected")

    def assert_filter_returns(self, params: dict, expected: list[Workflow]) -> None:
        """Проверяет, что список с фильтром содержит ровно ожидаемые workflow."""
        response = self.client.get(path=self.list_url, data=params)

        # Проверяем состав выдачи (порядок не важен)
        self.assertEqual(
            sorted(item["id"] for item in response.data["results"]),
            sorted(str(workflow.pk) for workflow in expected),
        )

    def test_filter_by_audience_is_base_and_active(self) -> None:
        """Фильтры audience, is_base и active выбирают нужные workflow."""
        base_b2b = WorkflowFactory(is_base=True, audience=Audience.B2B)
        b2c = WorkflowFactory(audience=Audience.B2C)
        inactive = WorkflowFactory(active=False)

        self.assert_filter_returns({"audience": Audience.B2C}, [b2c])
        self.assert_filter_returns({"is_base": "true"}, [base_b2b])
        self.assert_filter_returns({"active": "false"}, [inactive])

    def test_filter_by_created_by_ids(self) -> None:
        """Фильтр created_by__ids возвращает workflow указанных авторов."""
        author = UserFactory()
        target = WorkflowFactory(created_by=author)
        WorkflowFactory()

        self.assert_filter_returns({"created_by__ids": str(author.pk)}, [target])
