from sova.catalog.tests.factories import ProductFactory
from sova.interactions.tests.factories import InteractionProductFactory
from sova.processes.enum import StageInstanceContextType, StageInstanceStatus
from sova.processes.models import StageInstance
from sova.processes.services import workflow_engine_service as engine
from sova.processes.tests.base import EngineTestCase


class SyncContextsTestCase(EngineTestCase):
    """sync_contexts досоздаёт этапы для новых контекстов сразу, без ожидания complete_action."""

    def test_materializes_stage_for_product_added_after_start(self) -> None:
        # Этап взаимодействия держит процесс в работе: без контекстов продукта он завершился бы на старте
        self.builder.action(self.builder.stage("Подписание"), "Подписать")
        stage = self.builder.stage("Этап продукта", type=StageInstanceContextType.PRODUCT)
        self.builder.action(stage, "Передать лицензию")
        process = self.start()

        item = InteractionProductFactory(interaction=self.interaction, product=ProductFactory())

        # Проверяем, что без синхронизации этап для нового продукта ещё не создан
        self.assertFalse(
            StageInstance.objects.filter(workflow_instance=process, stage=stage, context_id=item.pk).exists()
        )

        engine.sync_contexts(process)

        # Проверяем, что этап создан и сразу открыт
        instance = StageInstance.objects.get(workflow_instance=process, stage=stage, context_id=item.pk)
        self.assertEqual(instance.status, StageInstanceStatus.IN_PROGRESS)
