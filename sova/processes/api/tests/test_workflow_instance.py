from datetime import datetime, timedelta, timezone

from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.tests.factories import B2CClientFactory
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import InteractionFactory
from sova.processes.models import WorkflowInstance
from sova.processes.tests.factories import WorkflowInstanceFactory
from sova.workflows.enum import Audience
from sova.workflows.tests.factories import WorkflowFactory


class WorkflowInstanceApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения и запуска процессов /api/processes/workflow-instances/."""

    url_basename = "processes:workflow-instance"
    model = WorkflowInstance
    allow_update = False
    allow_delete = False

    def create_instance(self, **kwargs) -> WorkflowInstance:
        """Создаёт процесс workflow."""
        return WorkflowInstanceFactory(**kwargs)

    def get_expected_data(self, instance: WorkflowInstance) -> dict:
        """Поля read-представления процесса."""
        creator = instance.created_by
        return {
            "id": str(instance.pk),
            "status": instance.status,
            "completed_at": None,
            "workflow": {
                "id": str(instance.workflow_id),
                "name": instance.workflow.name,
                "code": instance.workflow.code,
            },
            "interaction": {
                "id": str(instance.interaction_id),
                "university": {
                    "id": str(instance.interaction.university_id),
                    "name": instance.interaction.university.name,
                },
                "b2c_client": None,
            },
            "created_by": (
                {
                    "id": creator.pk,
                    "email": creator.email,
                    "full_name": creator.get_full_name(),
                }
                if creator
                else None
            ),
        }

    def get_post_data(self) -> dict:
        """Данные запуска процесса (workflow и взаимодействие — по id)."""
        return {
            "status": "running",
            "workflow": str(WorkflowFactory(audience=Audience.B2B).pk),
            "interaction": str(InteractionFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def test_add_sets_created_by(self) -> None:
        """Запуск проставляет автора из запроса."""
        response = self.client.post(
            path=self.list_url,
            data=self.get_post_data(),
            format="json",
        )

        # Проверяем автора
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["created_by"]["id"], self.user.pk)

    def test_add_for_b2c_client_requires_b2c_workflow(self) -> None:
        """Для взаимодействия с B2C-клиентом подходит только B2C-workflow."""
        interaction = InteractionFactory(university=None, b2c_client=B2CClientFactory())

        wrong = self.client.post(
            path=self.list_url,
            data={
                "status": "running",
                "workflow": str(WorkflowFactory(audience=Audience.B2B).pk),
                "interaction": str(interaction.pk),
            },
            format="json",
        )
        right = self.client.post(
            path=self.list_url,
            data={
                "status": "running",
                "workflow": str(WorkflowFactory(audience=Audience.B2C).pk),
                "interaction": str(interaction.pk),
            },
            format="json",
        )

        # Проверяем, что аудитория шаблона должна соответствовать контрагенту
        self.assertEqual(wrong.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workflow", wrong.data)
        self.assertEqual(right.status_code, status.HTTP_201_CREATED, msg=right.data)

    def test_add_returns_400_for_audience_mismatch_with_university(self) -> None:
        """B2C-workflow для взаимодействия с вузом отклоняется."""
        response = self.client.post(
            path=self.list_url,
            data={
                "status": "running",
                "workflow": str(WorkflowFactory(audience=Audience.B2C).pk),
                "interaction": str(InteractionFactory().pk),
            },
            format="json",
        )

        # Проверяем, что ошибка привязана к полю workflow
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workflow", response.data)

    def test_add_returns_400_for_inactive_workflow(self) -> None:
        """Запуск неактивного workflow отклоняется."""
        response = self.client.post(
            path=self.list_url,
            data={
                "status": "running",
                "workflow": str(WorkflowFactory(active=False).pk),
                "interaction": str(InteractionFactory().pk),
            },
            format="json",
        )

        # Проверяем, что ошибка привязана к полю workflow
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workflow", response.data)

    def assert_filter_returns(self, params: dict, expected: list[WorkflowInstance]) -> None:
        """Проверяет, что список с фильтром содержит ровно ожидаемые процессы."""
        response = self.client.get(path=self.list_url, data=params)

        # Проверяем состав выдачи (порядок не важен)
        self.assertEqual(
            sorted(item["id"] for item in response.data["results"]),
            sorted(str(instance.pk) for instance in expected),
        )

    def test_filters_select_matching_processes(self) -> None:
        """Фильтры workflow, interaction, university, status, автор выбирают нужные процессы."""
        author = UserFactory()
        target = WorkflowInstanceFactory(status="paused", created_by=author)
        WorkflowInstanceFactory()

        self.assert_filter_returns({"workflow__ids": str(target.workflow_id)}, [target])
        self.assert_filter_returns({"interaction__ids": str(target.interaction_id)}, [target])
        self.assert_filter_returns(
            {"university__ids": str(target.interaction.university_id)},
            [target],
        )
        self.assert_filter_returns({"status": "paused"}, [target])
        self.assert_filter_returns({"created_by__ids": str(author.pk)}, [target])

    def test_filter_is_completed(self) -> None:
        """Фильтр is_completed отделяет завершённые процессы от активных."""
        active = WorkflowInstanceFactory()
        done = WorkflowInstanceFactory(completed_at=datetime.now(tz=timezone.utc))

        self.assert_filter_returns({"is_completed": "true"}, [done])
        self.assert_filter_returns({"is_completed": "false"}, [active])

    def test_filter_by_started_period(self) -> None:
        """Фильтры started_at__gte/started_at__lte ограничивают период запуска."""
        now = datetime.now(tz=timezone.utc)
        old = WorkflowInstanceFactory()
        recent = WorkflowInstanceFactory()
        WorkflowInstance.objects.filter(pk=old.pk).update(started_at=now - timedelta(days=40))
        date_from = (now - timedelta(days=10)).date().isoformat()

        self.assert_filter_returns({"started_at__gte": date_from}, [recent])
        self.assert_filter_returns({"started_at__lte": date_from}, [old])
