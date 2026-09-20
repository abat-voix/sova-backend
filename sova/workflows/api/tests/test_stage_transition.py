import uuid

from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.processes.enum import StageInstanceContextType
from sova.workflows.models import StageTransition
from sova.workflows.tests.factories import (
    StageTransitionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class StageTransitionApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/stage-transitions/."""

    url_basename = "workflows:stage-transition"
    model = StageTransition

    def create_instance(self, **kwargs) -> StageTransition:
        """Создаёт связь между этапами; название этапа-источника уникально для теста поиска."""
        kwargs.setdefault("from_stage", WorkflowStageFactory(name=f"Источник {uuid.uuid4().hex}"))
        return StageTransitionFactory(**kwargs)

    def get_expected_data(self, instance: StageTransition) -> dict:
        """Поля read-представления связи."""
        return {
            "id": str(instance.pk),
            "active": instance.active,
            "from_stage": {
                "id": str(instance.from_stage_id),
                "name": instance.from_stage.name,
                "workflow": str(instance.from_stage.workflow_id),
            },
            "to_stage": {
                "id": str(instance.to_stage_id),
                "name": instance.to_stage.name,
                "workflow": str(instance.to_stage.workflow_id),
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания связи: оба этапа из одного workflow."""
        workflow = WorkflowFactory()
        source = WorkflowStageFactory(workflow=workflow)
        target = WorkflowStageFactory(workflow=workflow)
        return {"from_stage": str(source.pk), "to_stage": str(target.pk)}

    def get_change_data(self) -> dict:
        """Данные обновления связи."""
        return {"active": False}

    def get_search_term(self, instance: StageTransition) -> str:
        """Поиск по названию этапа-источника."""
        return instance.from_stage.name

    def post_transition(self, source, target, **extra):
        """Отправляет запрос на создание связи source → target."""
        return self.client.post(
            path=self.list_url,
            data={"from_stage": str(source.pk), "to_stage": str(target.pk), **extra},
            format="json",
        )

    def test_add_returns_400_for_transition_to_itself(self) -> None:
        """Связь этапа с самим собой возвращает 400."""
        stage = WorkflowStageFactory()

        response = self.post_transition(source=stage, target=stage)

        # Проверяем, что CheckConstraint не доходит до БД, а ошибка привязана к полю
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("to_stage", response.data)

    def test_add_returns_400_for_stages_from_different_workflows(self) -> None:
        """Связь между этапами разных workflow отклоняется."""
        response = self.post_transition(source=WorkflowStageFactory(), target=WorkflowStageFactory())

        # Проверяем ошибку по полю to_stage
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("to_stage", response.data)

    def test_add_returns_400_for_duplicate_pair(self) -> None:
        """Повтор пары «источник → цель» возвращает 400."""
        existing = StageTransitionFactory()

        response = self.post_transition(source=existing.from_stage, target=existing.to_stage)

        # Проверяем, что нарушение unique_stage_transition отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_for_direct_cycle(self) -> None:
        """Обратная связь (B→A при существующей A→B) образует цикл."""
        existing = StageTransitionFactory()

        response = self.post_transition(source=existing.to_stage, target=existing.from_stage)

        # Проверяем, что цикл отклонён и ошибка привязана к полю
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("to_stage", response.data)

    def test_add_returns_400_for_transitive_cycle(self) -> None:
        """Связь, замыкающая цепочку A→B→C→A, возвращает 400."""
        workflow = WorkflowFactory()
        a, b, c = WorkflowStageFactory.create_batch(size=3, workflow=workflow)
        StageTransitionFactory(from_stage=a, to_stage=b)
        StageTransitionFactory(from_stage=b, to_stage=c)

        response = self.post_transition(source=c, target=a)

        # Проверяем, что цикл найден через промежуточный этап
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_allows_diamond_without_cycle(self) -> None:
        """Ромб A→B, A→C, B→D, C→D циклом не считается."""
        workflow = WorkflowFactory()
        a, b, c, d = WorkflowStageFactory.create_batch(size=4, workflow=workflow)
        StageTransitionFactory(from_stage=a, to_stage=b)
        StageTransitionFactory(from_stage=a, to_stage=c)
        StageTransitionFactory(from_stage=b, to_stage=d)

        response = self.post_transition(source=c, target=d)

        # Проверяем, что общий предок не воспринимается как цикл
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_add_ignores_inactive_transitions_when_looking_for_cycle(self) -> None:
        """Неактивная обратная связь цикл не образует."""
        existing = StageTransitionFactory(active=False)

        response = self.post_transition(source=existing.to_stage, target=existing.from_stage)

        # Проверяем, что учитываются только активные связи
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_add_inactive_transition_is_not_checked_for_cycle(self) -> None:
        """Неактивную связь, которая замкнула бы цикл, можно сохранить: в графе она не участвует."""
        existing = StageTransitionFactory()

        response = self.post_transition(
            source=existing.to_stage,
            target=existing.from_stage,
            active=False,
        )

        # Проверяем, что связь создана
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_change_returns_400_when_reactivating_creates_cycle(self) -> None:
        """Включение связи, замыкающей цикл, возвращает 400."""
        first = StageTransitionFactory()
        reverse = StageTransitionFactory(
            from_stage=first.to_stage,
            to_stage=first.from_stage,
            active=False,
        )

        response = self.client.patch(
            path=self.detail_url(reverse),
            data={"active": True},
            format="json",
        )

        # Проверяем, что цикл ловится и при реактивации
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_does_not_treat_the_edited_transition_as_a_cycle(self) -> None:
        """Правка существующей связи не считает её же старое состояние причиной цикла."""
        transition = StageTransitionFactory()

        response = self.client.patch(
            path=self.detail_url(transition),
            data={"from_stage": str(transition.from_stage_id), "to_stage": str(transition.to_stage_id)},
            format="json",
        )

        # Проверяем, что правка прошла
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_add_returns_400_for_transition_from_program_stage_to_interaction_stage(self) -> None:
        """Этап взаимодействия не может идти после этапа программы, продукта или направления."""
        workflow = WorkflowFactory()
        product = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.IT_PRODUCT)
        interaction = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.INTERACTION)

        response = self.post_transition(source=product, target=interaction)

        # Проверяем ошибку по полю to_stage
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("to_stage", response.data)

    def test_add_allows_transition_from_interaction_stage_to_product_stage(self) -> None:
        """Этап продукта открывается после этапа взаимодействия."""
        workflow = WorkflowFactory()
        interaction = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.INTERACTION)
        product = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.IT_PRODUCT)

        response = self.post_transition(source=interaction, target=product)

        # Проверяем, что связь создана
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_filters_select_matching_transitions(self) -> None:
        """Фильтры этапов, workflow и активности выбирают нужные связи."""
        target = StageTransitionFactory(active=False)
        StageTransitionFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return [item["id"] for item in response.data["results"]]

        # Проверяем фильтр по этапу-источнику
        self.assertEqual(ids({"from_stage__ids": str(target.from_stage_id)}), [str(target.pk)])
        # Проверяем фильтр по этапу-цели
        self.assertEqual(ids({"to_stage__ids": str(target.to_stage_id)}), [str(target.pk)])
        # Проверяем фильтр по workflow через этап-источник
        self.assertEqual(ids({"workflow__ids": str(target.from_stage.workflow_id)}), [str(target.pk)])
        # Проверяем фильтр по активности
        self.assertEqual(ids({"active": "false"}), [str(target.pk)])
