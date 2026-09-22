from django.urls import reverse
from rest_framework import status

from sova.catalog.tests.factories import ProductFactory
from sova.interactions.models import Contract, Interaction, InteractionProduct
from sova.interactions.tests.factories import ContractFactory, InteractionProductFactory
from sova.processes.enum import StageInstanceStatus, WorkflowInstanceStatus
from sova.processes.models import StageInstance
from sova.processes.tests.base import PRODUCT, EngineApiTestCase


class CompositionSyncApiTestCase(EngineApiTestCase):
    """Изменение состава взаимодействия через API сразу отражается в его идущем процессе."""

    def setUp(self) -> None:
        """Workflow с этапом продукта; процесс держит в работе этап взаимодействия."""
        super().setUp()
        self.signing = self.builder.stage("Подписание")
        self.builder.action(self.signing, "Подписать")
        self.product_stage = self.builder.stage("Этап продукта", type=PRODUCT)
        self.builder.action(self.product_stage, "Передать лицензию")

    def test_create_product_materializes_stage(self) -> None:
        """Добавленный продукт сразу получает открытый этап."""
        process = self.start()

        response = self.client.post(
            path=reverse("interactions:interaction-product-list"),
            data={"interaction": str(self.interaction.pk), "product": str(ProductFactory().pk)},
            format="json",
        )

        # Проверяем, что этап продукта создан и открыт без завершения действий
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        instance = StageInstance.objects.get(
            workflow_instance=process, stage=self.product_stage, context_id=response.data["id"]
        )
        self.assertEqual(instance.status, StageInstanceStatus.IN_PROGRESS)

    def test_deactivate_last_context_completes_process(self) -> None:
        """Деактивация продукта, этап которого последний незакрытый, завершает процесс."""
        self.signing.is_active = False
        self.signing.save(update_fields=["is_active"])
        item = InteractionProductFactory(interaction=self.interaction)
        process = self.start()

        response = self.client.patch(
            path=reverse("interactions:interaction-product-detail", args=[item.pk]),
            data={"is_active": False},
            format="json",
        )

        # Проверяем, что процесс завершился сразу, а не при следующем действии
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        process.refresh_from_db()
        self.assertEqual(process.status, WorkflowInstanceStatus.COMPLETED)

    def test_delete_last_context_completes_process(self) -> None:
        """Удаление продукта, этап которого последний незакрытый, завершает процесс."""
        self.signing.is_active = False
        self.signing.save(update_fields=["is_active"])
        item = InteractionProductFactory(interaction=self.interaction)
        process = self.start()

        response = self.client.delete(path=reverse("interactions:interaction-product-detail", args=[item.pk]))

        # Проверяем, что процесс завершился сразу
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        process.refresh_from_db()
        self.assertEqual(process.status, WorkflowInstanceStatus.COMPLETED)


class ContractAttachmentApiTestCase(EngineApiTestCase):
    """Привязка безголового договора через /api/interactions/contracts/{id}/attach-to-new-interaction/."""

    def setUp(self) -> None:
        """Безголовый договор с одним безголовым продуктом."""
        super().setUp()
        self.contract = ContractFactory(interaction=None, university=self.interaction.university)
        self.item = InteractionProductFactory(contract=self.contract, interaction=None)

    def attach_new_url(self, contract: Contract) -> str:
        return reverse("interactions:contract-attach-to-new-interaction", args=[contract.pk])

    def test_attach_already_attached_returns_409(self) -> None:
        """Повторная привязка договора возвращает 409."""
        contract = ContractFactory(interaction=self.interaction)

        response = self.client.post(path=self.attach_new_url(contract))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "contract_already_attached")

    def test_attach_to_new_interaction(self) -> None:
        """Привязка к новому взаимодействию создаёт его с контрагентом договора и переносит продукт."""
        response = self.client.post(path=self.attach_new_url(self.contract))

        # Проверяем, что создано новое взаимодействие вуза договора и продукт перешёл на него
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        interaction = Interaction.objects.get(pk=response.data["interaction"]["id"])
        self.assertNotEqual(interaction.pk, self.interaction.pk)
        self.assertEqual(interaction.university_id, self.contract.university_id)
        self.assertEqual(InteractionProduct.objects.get(pk=self.item.pk).interaction_id, interaction.pk)

    def test_attach_to_new_interaction_with_unknown_manager_returns_409(self) -> None:
        """ФИО менеджера не найдено — 409, взаимодействие не создано."""
        self.contract.draft_manager_full_name = "Несуществующий Менеджер"
        self.contract.save(update_fields=["draft_manager_full_name"])
        interactions_before = Interaction.objects.count()

        response = self.client.post(path=self.attach_new_url(self.contract))

        # Проверяем, что транзакция откатилась целиком
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "manager_not_found")
        self.assertEqual(Interaction.objects.count(), interactions_before)
        self.contract.refresh_from_db()
        self.assertIsNone(self.contract.interaction_id)
