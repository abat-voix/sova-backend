from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.processes.enum import StageInstanceContextType
from sova.workflows.models import WorkflowStage
from sova.workflows.tests.factories import (
    StageTransitionFactory,
    WorkflowFactory,
    WorkflowStageFactory,
)


class WorkflowStageApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/workflow-stages/."""

    url_basename = "workflows:workflow-stage"
    model = WorkflowStage

    def create_instance(self, **kwargs) -> WorkflowStage:
        """Создаёт этап workflow."""
        return WorkflowStageFactory(**kwargs)

    def get_expected_data(self, instance: WorkflowStage) -> dict:
        """Поля read-представления этапа."""
        return {
            "id": str(instance.pk),
            "name": instance.name,
            "type": instance.type,
            "description": instance.description,
            "sort_order": instance.sort_order,
            "is_initial": instance.is_initial,
            "is_final": instance.is_final,
            "is_optional": instance.is_optional,
            "is_active": instance.is_active,
            "workflow": {
                "id": str(instance.workflow_id),
                "name": instance.workflow.name,
                "code": instance.workflow.code,
            },
        }

    def get_post_data(self) -> dict:
        """Данные создания этапа (workflow — по id)."""
        return {
            "name": "Поиск контактов",
            "sort_order": 1,
            "workflow": str(WorkflowFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления этапа."""
        return {"name": "Коммуникация", "is_optional": True}

    def get_search_term(self, instance: WorkflowStage) -> str:
        """Поиск по названию."""
        return instance.name

    def test_add_returns_400_with_duplicate_sort_order(self) -> None:
        """Повтор порядкового номера в workflow возвращает 400."""
        existing = WorkflowStageFactory(sort_order=5)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Дубль порядка",
                "sort_order": 5,
                "workflow": str(existing.workflow_id),
            },
            format="json",
        )

        # Проверяем, что нарушение unique_workflow_stage_order отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_second_initial_stage_returns_400(self) -> None:
        """Второй начальный этап в workflow отклоняется с 400."""
        existing = WorkflowStageFactory(is_initial=True)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Ещё начальный",
                "sort_order": 99,
                "is_initial": True,
                "workflow": str(existing.workflow_id),
            },
            format="json",
        )

        # Проверяем, что условное ограничение ловится валидацией
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_initial", response.data)

    def test_add_initial_stage_in_another_workflow_creates_stage(self) -> None:
        """Начальные этапы разных workflow сосуществуют."""
        WorkflowStageFactory(is_initial=True)

        response = self.client.post(
            path=self.list_url,
            data={
                "name": "Начальный в другом",
                "sort_order": 1,
                "is_initial": True,
                "workflow": str(WorkflowFactory().pk),
            },
            format="json",
        )

        # Проверяем, что ограничение действует только в рамках одного workflow
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)

    def test_change_initial_stage_keeps_flag(self) -> None:
        """Обновление самого начального этапа не конфликтует с его же флагом."""
        initial = WorkflowStageFactory(is_initial=True)

        response = self.client.patch(
            path=self.detail_url(initial),
            data={"name": "Новое имя", "is_initial": True},
            format="json",
        )

        # Проверяем, что собственный флаг is_initial не считается конфликтом
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_add_accepts_each_fixed_type(self) -> None:
        """Тип этапа принимает значения взаимодействия, направления, программы и продукта."""
        workflow = WorkflowFactory()

        for order, stage_type in enumerate(StageInstanceContextType.values, start=1):
            response = self.client.post(
                path=self.list_url,
                data={
                    "name": f"Этап {stage_type}",
                    "sort_order": order,
                    "type": stage_type,
                    "workflow": str(workflow.pk),
                },
                format="json",
            )

            # Проверяем, что этап создан с указанным типом
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
            self.assertEqual(response.data["type"], stage_type)

    def test_add_without_type_defaults_to_interaction(self) -> None:
        """Этап без указанного типа создаётся как этап взаимодействия."""
        response = self.client.post(
            path=self.list_url,
            data=self.get_post_data(),
            format="json",
        )

        # Проверяем тип по умолчанию
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["type"], StageInstanceContextType.INTERACTION)

    def test_add_returns_400_with_free_text_type(self) -> None:
        """Тип этапа вне фиксированного набора возвращает 400."""
        data = self.get_post_data()
        data["type"] = "Продукт"

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что ошибка привязана к полю type
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("type", response.data)

    def test_filter_by_type(self) -> None:
        """Фильтр type возвращает этапы указанного типа."""
        workflow = WorkflowFactory()
        product = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.PRODUCT)
        WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.PROGRAM)

        response = self.client.get(
            path=self.list_url,
            data={"type": StageInstanceContextType.PRODUCT},
        )

        # Проверяем, что найден только этап продукта
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(product.pk)],
        )

    def test_filter_by_workflow_ids_and_flags(self) -> None:
        """Фильтры workflow__ids, is_initial, is_final выбирают нужные этапы."""
        workflow = WorkflowFactory()
        first = WorkflowStageFactory(workflow=workflow, is_initial=True)
        last = WorkflowStageFactory(workflow=workflow, is_final=True)
        WorkflowStageFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return sorted(item["id"] for item in response.data["results"])

        # Проверяем фильтр по workflow
        self.assertEqual(
            ids({"workflow__ids": str(workflow.pk)}),
            sorted([str(first.pk), str(last.pk)]),
        )
        # Проверяем фильтры по признакам
        self.assertEqual(ids({"is_initial": "true"}), [str(first.pk)])
        self.assertEqual(ids({"is_final": "true"}), [str(last.pk)])

    def patch_stage(self, stage, **data):
        """Отправляет PATCH этапа."""
        return self.client.patch(path=self.detail_url(stage), data=data, format="json")

    def test_change_returns_400_when_moving_stage_with_transitions_to_another_workflow(self) -> None:
        """Этап с активными связями нельзя перенести в другой workflow: связь вышла бы за workflow."""
        transition = StageTransitionFactory()

        response = self.patch_stage(transition.from_stage, workflow=str(WorkflowFactory().pk))

        # Проверяем ошибку по полю workflow
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workflow", response.data)

    def test_change_returns_400_when_moving_target_stage_to_another_workflow(self) -> None:
        """Этап-цель активной связи тоже нельзя перенести в другой workflow."""
        transition = StageTransitionFactory()

        response = self.patch_stage(transition.to_stage, workflow=str(WorkflowFactory().pk))

        # Проверяем ошибку по полю workflow
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("workflow", response.data)

    def test_change_allows_moving_stage_with_only_inactive_transitions(self) -> None:
        """Неактивные связи перенос не блокируют."""
        transition = StageTransitionFactory(is_active=False)

        response = self.patch_stage(transition.from_stage, workflow=str(WorkflowFactory().pk))

        # Проверяем, что перенос выполнен
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_allows_moving_stage_without_transitions(self) -> None:
        """Этап без связей переносится в другой workflow свободно."""
        stage = WorkflowStageFactory()

        response = self.patch_stage(stage, workflow=str(WorkflowFactory().pk))

        # Проверяем, что перенос выполнен
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_allows_source_type_to_become_product_before_interaction_stage(self) -> None:
        """Источник связи можно сделать этапом продукта, даже если после него идёт этап взаимодействия."""
        transition = StageTransitionFactory()

        response = self.patch_stage(transition.from_stage, type=StageInstanceContextType.PRODUCT)

        # Проверяем, что смена типа выполнена
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_allows_target_type_to_become_interaction_after_product_stage(self) -> None:
        """Цель связи можно сделать этапом взаимодействия, даже если перед ней идёт этап продукта."""
        workflow = WorkflowFactory()
        source = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.PRODUCT)
        target = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.PRODUCT)
        StageTransitionFactory(from_stage=source, to_stage=target)

        response = self.patch_stage(target, type=StageInstanceContextType.INTERACTION)

        # Проверяем, что смена типа выполнена
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_change_allows_type_change_that_keeps_transitions_valid(self) -> None:
        """Смена типа, не нарушающая правило, проходит."""
        workflow = WorkflowFactory()
        source = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.INTERACTION)
        target = WorkflowStageFactory(workflow=workflow, type=StageInstanceContextType.PRODUCT)
        StageTransitionFactory(from_stage=source, to_stage=target)

        response = self.patch_stage(source, type=StageInstanceContextType.PRODUCT)

        # Проверяем, что смена типа выполнена
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
