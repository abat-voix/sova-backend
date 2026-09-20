from datetime import datetime, timedelta, timezone

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.tests.factories import B2CClientFactory
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import InteractionFactory, InteractionProductFactory
from sova.processes.enum import StageInstanceStatus, WorkflowInstanceStatus
from sova.processes.models import StageInstance, WorkflowInstance
from sova.processes.tests.base import PRODUCT, EngineApiTestCase
from sova.processes.tests.factories import WorkflowInstanceFactory
from sova.workflows.enum import Audience
from sova.workflows.tests.builders import WorkflowBuilder
from sova.workflows.tests.factories import WorkflowFactory


def startable_workflow(audience: str = Audience.B2B):
    """Workflow с одним этапом и одним действием — его можно запустить."""
    builder = WorkflowBuilder(audience=audience)
    builder.action(builder.stage("Поиск контактов"), "Найти контакт")
    return builder.workflow


class WorkflowInstanceApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения и запуска процессов /api/processes/workflow-instances/: запуск идёт через движок."""

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
            "workflow": str(startable_workflow().pk),
            "interaction": str(InteractionFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def post(self, workflow, interaction, **extra):
        """Запускает процесс."""
        return self.client.post(
            path=self.list_url,
            data={"workflow": str(workflow.pk), "interaction": str(interaction.pk), **extra},
            format="json",
        )

    def test_add_sets_created_by(self) -> None:
        """Запуск проставляет автора из запроса."""
        response = self.client.post(path=self.list_url, data=self.get_post_data(), format="json")

        # Проверяем автора
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["created_by"]["id"], self.user.pk)

    def test_add_creates_stage_instances_and_opens_initial_stage(self) -> None:
        """Запуск создаёт экземпляры этапов и открывает начальный этап."""
        response = self.client.post(path=self.list_url, data=self.get_post_data(), format="json")

        stage_instance = StageInstance.objects.get(workflow_instance=response.data["id"])
        # Проверяем, что этап открыт
        self.assertEqual(stage_instance.status, StageInstanceStatus.IN_PROGRESS)

    def test_add_ignores_status_from_request(self) -> None:
        """Статус процесса задаёт движок, а не запрос."""
        response = self.client.post(
            path=self.list_url,
            data={**self.get_post_data(), "status": "completed"},
            format="json",
        )

        # Проверяем статус
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["status"], WorkflowInstanceStatus.RUNNING)

    def test_add_for_b2c_client_requires_b2c_workflow(self) -> None:
        """Для взаимодействия с B2C-клиентом подходит только B2C-workflow."""
        interaction = InteractionFactory(university=None, b2c_client=B2CClientFactory())

        wrong = self.post(startable_workflow(audience=Audience.B2B), interaction)
        right = self.post(startable_workflow(audience=Audience.B2C), interaction)

        # Проверяем, что аудитория шаблона должна соответствовать контрагенту
        self.assertEqual(wrong.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(wrong.data["code"], "audience_mismatch")
        self.assertEqual(right.status_code, status.HTTP_201_CREATED, msg=right.data)

    def test_add_returns_400_for_audience_mismatch_with_university(self) -> None:
        """B2C-workflow для взаимодействия с вузом отклоняется."""
        response = self.post(startable_workflow(audience=Audience.B2C), InteractionFactory())

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "audience_mismatch")

    def test_add_returns_400_for_inactive_workflow(self) -> None:
        """Запуск неактивного workflow отклоняется."""
        workflow = startable_workflow()
        workflow.active = False
        workflow.save()

        response = self.post(workflow, InteractionFactory())

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "workflow_inactive")

    def test_add_returns_400_for_workflow_without_stages(self) -> None:
        """Пустой workflow запустить нельзя."""
        response = self.post(WorkflowFactory(), InteractionFactory())

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "empty_workflow")

    def test_add_returns_409_when_workflow_already_started_for_interaction(self) -> None:
        """Повторный запуск того же workflow для взаимодействия возвращает 409."""
        workflow = startable_workflow()
        interaction = InteractionFactory()
        self.post(workflow, interaction)

        response = self.post(workflow, interaction)

        # Проверяем статус, код и то, что процесс один
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "already_started")
        self.assertEqual(WorkflowInstance.objects.count(), 1)

    def test_add_returns_400_without_workflow_or_interaction(self) -> None:
        """Без workflow и взаимодействия: 400 и ошибки по полям."""
        response = self.client.post(path=self.list_url, data={}, format="json")

        # Проверяем ошибки полей
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workflow", response.data)
        self.assertIn("interaction", response.data)

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
        target = WorkflowInstanceFactory(status="completed", created_by=author)
        WorkflowInstanceFactory()

        self.assert_filter_returns({"workflow__ids": str(target.workflow_id)}, [target])
        self.assert_filter_returns({"interaction__ids": str(target.interaction_id)}, [target])
        self.assert_filter_returns(
            {"university__ids": str(target.interaction.university_id)},
            [target],
        )
        self.assert_filter_returns({"status": "completed"}, [target])
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


class WorkflowBoardApiTestCase(EngineApiTestCase):
    """Тесты GET /api/processes/workflow-instances/{id}/board/: доска процесса для визуализации."""

    def setUp(self) -> None:
        """Подписание, после него этап продукта; у взаимодействия один продукт."""
        super().setUp()
        self.signing = self.builder.stage("Подписание")
        self.sign = self.builder.action(self.signing, "Подписать")
        self.product_stage = self.builder.stage("Продукт", after=(self.signing,), type=PRODUCT)
        self.transfer = self.builder.action(self.product_stage, "Передать лицензию")
        self.product = InteractionProductFactory(interaction=self.interaction)
        self.process = self.start()

    def url(self, process=None) -> str:
        """URL доски процесса."""
        return reverse("processes:workflow-instance-board", args=[(process or self.process).pk])

    def test_board_describes_process_stages_and_actions(self) -> None:
        """Доска отдаёт шапку, этапы взаимодействия с действиями и исходами и группы по контекстам."""
        response = self.client.get(path=self.url())

        # Проверяем успешный ответ и шапку
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["id"], str(self.process.pk))
        self.assertEqual(response.data["status"], WorkflowInstanceStatus.RUNNING)
        self.assertEqual(response.data["workflow"]["id"], str(self.builder.workflow.pk))
        self.assertEqual(response.data["interaction"]["id"], str(self.interaction.pk))
        # Проверяем этап взаимодействия, его действие и исход
        stage = response.data["interaction_stages"][0]
        self.assertEqual(stage["stage"]["name"], "Подписание")
        self.assertEqual(stage["status"], StageInstanceStatus.IN_PROGRESS)
        action = stage["actions"][0]
        self.assertEqual(action["name"], "Подписать")
        self.assertEqual(action["status"], "in_progress")
        self.assertEqual([item["code"] for item in action["available_outcomes"]], ["done"])
        # Проверяем группу продукта
        group = response.data["context_groups"][0]
        self.assertEqual(group["context_type"], PRODUCT)
        self.assertEqual(group["context_id"], str(self.product.pk))
        self.assertEqual(group["title"], self.product.it_product.name)
        self.assertEqual(group["stages"][0]["status"], StageInstanceStatus.PENDING)

    def test_board_reflects_progress_after_completing_action(self) -> None:
        """После завершения действия доска показывает открытый этап продукта и вариант возврата."""
        self.complete(self.process, self.sign)

        response = self.client.get(path=self.url())

        group = response.data["context_groups"][0]
        # Проверяем открытый этап продукта, его действие и вариант возврата
        self.assertEqual(group["stages"][0]["status"], StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(group["stages"][0]["actions"][0]["status"], "in_progress")
        self.assertEqual(
            group["stages"][0]["return_options"],
            [{"id": str(self.stage_instance(self.process, self.signing).pk), "stage_name": "Подписание"}],
        )
        # Проверяем результат закрытого этапа
        signed = response.data["interaction_stages"][0]["actions"][0]
        self.assertEqual(signed["status"], "completed")
        self.assertEqual(signed["result"]["outcome_name"], "Выполнено")
        self.assertEqual(signed["result"]["created_by"]["id"], self.user.pk)

    def test_board_returns_404_for_unknown_process(self) -> None:
        """Несуществующий процесс: 404."""
        response = self.client.get(path=self.url(process=WorkflowInstanceFactory.build()))

        # Проверяем статус
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_board_requires_authentication(self) -> None:
        """Анонимный запрос отклоняется."""
        self.client.force_authenticate(user=None)

        response = self.client.get(path=self.url())

        # Проверяем, что доступ запрещён
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
