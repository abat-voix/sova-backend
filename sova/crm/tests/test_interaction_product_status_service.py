from django.test import TestCase

from sova.crm.models import InteractionProductStatus
from sova.crm.services import InteractionProductStatusService
from sova.crm.tests.factories import (
    InteractionFactory,
    InteractionProductFactory,
    WorkflowInstanceFactory,
    WorkflowStatusFactory,
    WorkflowTemplateFactory,
)


class GetOrCreateProgressTestCase(TestCase):
    """Тесты InteractionProductStatusService.get_or_create_progress."""

    def setUp(self) -> None:
        """Готовит статус с подстатусом и сделку с двумя продуктами на этом статусе."""
        self.template = WorkflowTemplateFactory()
        self.parent_status = WorkflowStatusFactory(template=self.template, order=1)
        self.substatus = WorkflowStatusFactory(
            template=self.template, parent=self.parent_status, order=1, is_initial=True,
        )
        self.interaction = InteractionFactory()
        self.product1 = InteractionProductFactory(interaction=self.interaction)
        self.product2 = InteractionProductFactory(interaction=self.interaction)
        self.instance = WorkflowInstanceFactory(
            interaction=self.interaction, template=self.template, current_status=self.parent_status,
        )

    def test_creates_progress_for_active_products_on_initial_substatus(self) -> None:
        """Для активных продуктов сделки создаётся прогресс на начальном подстатусе."""
        progress = InteractionProductStatusService.get_or_create_progress(self.instance)

        self.assertEqual({p.interaction_product_id for p in progress}, {self.product1.id, self.product2.id})
        self.assertTrue(all(p.current_status_id == self.substatus.id for p in progress))

    def test_ignores_inactive_products(self) -> None:
        """Деактивированные продукты не получают строку прогресса."""
        self.product2.is_active = False
        self.product2.save(update_fields=["is_active"])

        progress = InteractionProductStatusService.get_or_create_progress(self.instance)

        self.assertEqual({p.interaction_product_id for p in progress}, {self.product1.id})

    def test_second_call_does_not_duplicate_rows(self) -> None:
        """Повторный вызов не создаёт дубликаты строк прогресса."""
        InteractionProductStatusService.get_or_create_progress(self.instance)
        InteractionProductStatusService.get_or_create_progress(self.instance)

        self.assertEqual(InteractionProductStatus.objects.filter(interaction_product__interaction=self.interaction).count(), 2)

    def test_returns_empty_when_status_has_no_substatuses(self) -> None:
        """У статуса без подстатусов прогресс продуктов не создаётся."""
        flat_status = WorkflowStatusFactory(template=self.template, order=2)
        instance = WorkflowInstanceFactory(
            interaction=InteractionFactory(), template=self.template, current_status=flat_status,
        )

        progress = InteractionProductStatusService.get_or_create_progress(instance)

        self.assertEqual(progress, [])


class IsCompleteTestCase(TestCase):
    """Тесты InteractionProductStatusService.is_complete."""

    def setUp(self) -> None:
        """Готовит статус с двумя подстатусами (начальный + финальный) и сделку с продуктом."""
        self.template = WorkflowTemplateFactory()
        self.parent_status = WorkflowStatusFactory(template=self.template, order=1)
        self.substatus_start = WorkflowStatusFactory(
            template=self.template, parent=self.parent_status, order=1, is_initial=True,
        )
        self.substatus_final = WorkflowStatusFactory(
            template=self.template, parent=self.parent_status, order=2, is_final=True,
        )
        self.interaction = InteractionFactory()
        self.product = InteractionProductFactory(interaction=self.interaction)
        self.instance = WorkflowInstanceFactory(
            interaction=self.interaction, template=self.template, current_status=self.parent_status,
        )

    def test_true_when_status_has_no_substatuses(self) -> None:
        """У статуса без подстатусов сделка всегда считается готовой к переходу."""
        flat_status = WorkflowStatusFactory(template=self.template, order=2)
        instance = WorkflowInstanceFactory(
            interaction=InteractionFactory(), template=self.template, current_status=flat_status,
        )

        self.assertTrue(InteractionProductStatusService.is_complete(instance))

    def test_true_when_no_active_products(self) -> None:
        """У сделки без активных продуктов проверка завершённости проходит автоматически."""
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        self.assertTrue(InteractionProductStatusService.is_complete(self.instance))

    def test_false_when_progress_missing(self) -> None:
        """Прогресс ещё не создавался — считается незавершённым."""
        self.assertFalse(InteractionProductStatusService.is_complete(self.instance))

    def test_false_when_product_not_on_final_substatus(self) -> None:
        """Продукт создан, но не дошёл до финального подстатуса — не завершено."""
        InteractionProductStatusService.get_or_create_progress(self.instance)

        self.assertFalse(InteractionProductStatusService.is_complete(self.instance))

    def test_true_when_all_active_products_on_final_substatus(self) -> None:
        """Все активные продукты на финальном подстатусе — завершено."""
        progress = InteractionProductStatusService.get_or_create_progress(self.instance)[0]
        progress.current_status = self.substatus_final
        progress.save(update_fields=["current_status"])

        self.assertTrue(InteractionProductStatusService.is_complete(self.instance))
