import uuid
from datetime import datetime, timezone

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.processes.enum import RollbackMode, StageInstanceContextType, StageInstanceStatus
from sova.processes.models import StageInstance, StageRollback
from sova.processes.tests.base import IN_PROGRESS, EngineApiTestCase
from sova.processes.tests.factories import StageInstanceFactory, WorkflowInstanceFactory


class StageInstanceApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения /api/processes/stage-instances/: состояние этапов меняет только движок."""

    url_basename = "processes:stage-instance"
    model = StageInstance
    allow_create = False
    allow_update = False
    allow_delete = False

    def create_instance(self, **kwargs) -> StageInstance:
        """Создаёт экземпляр этапа."""
        return StageInstanceFactory(**kwargs)

    def get_expected_data(self, instance: StageInstance) -> dict:
        """Поля read-представления экземпляра этапа."""
        return {
            "id": str(instance.pk),
            "context_type": instance.context_type,
            "context_id": instance.context_id and str(instance.context_id),
            "status": instance.status,
            "started_at": None,
            "completed_at": None,
            "workflow_instance": str(instance.workflow_instance_id),
            "stage": {
                "id": str(instance.stage_id),
                "name": instance.stage.name,
                "workflow": str(instance.stage.workflow_id),
            },
        }

    def get_post_data(self) -> dict:
        """Создание не поддерживается."""
        return {}

    def get_change_data(self) -> dict:
        """Обновление не поддерживается."""
        return {}

    def assert_filter_returns(self, params: dict, expected: list[StageInstance]) -> None:
        """Проверяет, что список с фильтром содержит ровно ожидаемые экземпляры."""
        response = self.client.get(path=self.list_url, data=params)

        # Проверяем состав выдачи (порядок не важен)
        self.assertEqual(
            sorted(item["id"] for item in response.data["results"]),
            sorted(str(instance.pk) for instance in expected),
        )

    def test_filters_select_matching_stage_instances(self) -> None:
        """Фильтры процесса, взаимодействия, этапа, контекста и статуса выбирают нужное."""
        target = StageInstanceFactory(
            status="completed",
            context_type=StageInstanceContextType.INTERACTION,
            context_id=None,
        )
        StageInstanceFactory()

        self.assert_filter_returns(
            {"workflow_instance__ids": str(target.workflow_instance_id)},
            [target],
        )
        self.assert_filter_returns(
            {"interaction__ids": str(target.workflow_instance.interaction_id)},
            [target],
        )
        self.assert_filter_returns({"stage__ids": str(target.stage_id)}, [target])
        self.assert_filter_returns({"status": "completed"}, [target])

    def test_filter_by_context_type_and_id(self) -> None:
        """Фильтры context_type и context_id находят экземпляры этапа по контексту."""
        process = WorkflowInstanceFactory()
        target = StageInstanceFactory(
            workflow_instance=process,
            context_type=StageInstanceContextType.INTERACTION,
            context_id=process.interaction_id,
        )
        StageInstanceFactory()

        self.assert_filter_returns(
            {
                "context_type": StageInstanceContextType.INTERACTION,
                "context_id": str(process.interaction_id),
            },
            [target],
        )

    def test_filter_is_completed(self) -> None:
        """Фильтр is_completed отделяет завершённые этапы от активных."""
        active = StageInstanceFactory()
        done = StageInstanceFactory(completed_at=datetime.now(tz=timezone.utc))

        self.assert_filter_returns({"is_completed": "true"}, [done])
        self.assert_filter_returns({"is_completed": "false"}, [active])


class CancelStageApiTestCase(EngineApiTestCase):
    """Тесты POST /api/processes/stage-instances/{id}/cancel/: отмена этапа и откат на предыдущий."""

    def setUp(self) -> None:
        """Цепочка из трёх этапов; процесс доведён до открытого третьего."""
        super().setUp()
        self.first = self.builder.stage("Первый")
        self.second = self.builder.stage("Второй", after=(self.first,))
        self.third = self.builder.stage("Третий", after=(self.second,))
        self.a1 = self.builder.action(self.first, "А1")
        self.a2 = self.builder.action(self.second, "А2")
        self.a3 = self.builder.action(self.third, "А3")
        self.process = self.start()
        self.complete(self.process, self.a1)
        self.complete(self.process, self.a2)

    def url(self, stage, context=None) -> str:
        """URL отмены экземпляра этапа."""
        return reverse("processes:stage-instance-cancel", args=[self.stage_instance(self.process, stage, context).pk])

    def post(self, stage, **data):
        """Отменяет этап; режим и причина по умолчанию заданы."""
        data.setdefault("mode", RollbackMode.RESTART)
        data.setdefault("reason", "Клиент передумал")
        return self.client.post(path=self.url(stage), data=data, format="json")

    def test_cancel_returns_rollback_and_changed_stages(self) -> None:
        """Ответ описывает запись журнала, этап возврата и сброшенные этапы."""
        response = self.post(self.third, mode=RollbackMode.LAST_ONLY)

        # Проверяем успешный ответ и запись журнала
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["rollback"]["reason"], "Клиент передумал")
        self.assertEqual(response.data["rollback"]["mode"], RollbackMode.LAST_ONLY)
        self.assertEqual(response.data["rollback"]["created_by"]["id"], self.user.pk)
        # Проверяем этап возврата и сброшенные этапы
        self.assertEqual(response.data["returned_stage"]["id"], str(self.stage_instance(self.process, self.second).pk))
        self.assertEqual(response.data["returned_stage"]["status"], StageInstanceStatus.IN_PROGRESS)
        self.assertEqual(
            [item["id"] for item in response.data["reset_stages"]],
            [str(self.stage_instance(self.process, self.third).pk)],
        )
        # Проверяем состояние в базе
        self.assertEqual(self.stage_status(self.process, self.third), StageInstanceStatus.PENDING)
        self.assertEqual(self.action_status(self.process, self.a2), IN_PROGRESS)
        self.assertEqual(StageRollback.objects.count(), 1)

    def test_cancel_in_restart_mode_resets_previous_actions(self) -> None:
        """Режим «заново» возвращает предыдущий этап целиком с новым исполнением действия."""
        self.post(self.third, mode=RollbackMode.RESTART)

        # Проверяем новое исполнение действия предыдущего этапа
        self.assertEqual(self.action_instance(self.process, self.a2).execution_no, 2)
        self.assertEqual(self.action_status(self.process, self.a2), IN_PROGRESS)

    def test_cancel_returns_409_for_stage_that_is_not_in_progress(self) -> None:
        """Закрытый и ожидающий этапы отменить нельзя: 409 и код invalid_state."""
        closed = self.post(self.second)
        # Проверяем закрытый этап
        self.assertEqual(closed.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(closed.data["code"], "invalid_state")

        cancelled = self.post(self.third)
        repeated = self.post(self.third)

        # Проверяем, что открытый этап отменился, а повторная отмена ожидающего отклонена
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK, msg=cancelled.data)
        self.assertEqual(repeated.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(repeated.data["code"], "invalid_state")

    def test_cancel_returns_400_for_first_stage_without_predecessor(self) -> None:
        """У первого этапа нет предшественника: 400 и код no_predecessor."""
        process = self.process
        self.cancel(process, self.third)
        self.cancel(process, self.second)

        response = self.post(self.first)

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "no_predecessor")

    def test_cancel_returns_400_for_blank_reason_and_invalid_mode(self) -> None:
        """Пустая причина и неизвестный режим отклоняются с ошибками по полям."""
        blank = self.post(self.third, reason="   ")
        no_reason = self.client.post(path=self.url(self.third), data={"mode": RollbackMode.RESTART}, format="json")
        bad_mode = self.post(self.third, mode="skip")

        # Проверяем ошибки полей
        self.assertEqual(blank.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", blank.data)
        self.assertEqual(no_reason.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", no_reason.data)
        self.assertEqual(bad_mode.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mode", bad_mode.data)
        self.assertEqual(self.stage_status(self.process, self.third), IN_PROGRESS)

    def test_cancel_returns_400_for_return_stage_that_is_not_a_predecessor(self) -> None:
        """Этап возврата не из предшественников: 400 и код invalid_return_to."""
        response = self.post(self.third, return_to=str(self.stage_instance(self.process, self.first).pk))

        # Проверяем статус и код
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_return_to")

    def test_cancel_returns_404_for_unknown_stage_instance(self) -> None:
        """Несуществующий экземпляр этапа: 404."""
        response = self.client.post(
            path=reverse("processes:stage-instance-cancel", args=[uuid.uuid4()]),
            data={"mode": RollbackMode.RESTART, "reason": "Ошибка"},
            format="json",
        )

        # Проверяем статус
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancel_requires_authentication(self) -> None:
        """Анонимный запрос отклоняется."""
        self.client.force_authenticate(user=None)

        response = self.post(self.third)

        # Проверяем, что доступ запрещён
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class CancelStageWithSeveralPredecessorsApiTestCase(EngineApiTestCase):
    """Тесты отмены этапа, в который ведут два этапа: этап возврата выбирает пользователь."""

    def setUp(self) -> None:
        """Два независимых этапа и общий этап после них; процесс доведён до открытого общего этапа."""
        super().setUp()
        self.left = self.builder.stage("Левый")
        self.right = self.builder.stage("Правый")
        self.joint = self.builder.stage("Общий", after=(self.left, self.right))
        left_action = self.builder.action(self.left, "Л")
        right_action = self.builder.action(self.right, "П")
        self.builder.action(self.joint, "О")
        self.process = self.start()
        self.complete(self.process, left_action)
        self.complete(self.process, right_action)
        self.url = reverse(
            "processes:stage-instance-cancel",
            args=[self.stage_instance(self.process, self.joint).pk],
        )

    def test_cancel_returns_400_without_choice(self) -> None:
        """Без return_to: 400 и код return_to_required, откат не выполнен."""
        response = self.client.post(
            path=self.url,
            data={"mode": RollbackMode.RESTART, "reason": "Ошибка"},
            format="json",
        )

        # Проверяем статус, код и то, что этап остался открытым
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "return_to_required")
        self.assertEqual(self.stage_status(self.process, self.joint), IN_PROGRESS)

    def test_cancel_returns_to_chosen_stage(self) -> None:
        """С return_to процесс возвращается на выбранный этап, второй остаётся закрытым."""
        chosen = self.stage_instance(self.process, self.left)

        response = self.client.post(
            path=self.url,
            data={"mode": RollbackMode.RESTART, "reason": "Ошибка", "return_to": str(chosen.pk)},
            format="json",
        )

        # Проверяем этап возврата и состояние этапов
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["returned_stage"]["id"], str(chosen.pk))
        self.assertEqual(self.stage_status(self.process, self.left), IN_PROGRESS)
        self.assertEqual(self.stage_status(self.process, self.right), StageInstanceStatus.COMPLETED)
