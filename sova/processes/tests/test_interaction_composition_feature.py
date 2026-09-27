from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import DirectionFactory, ProductFactory, ProgramFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import (
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
)
from sova.interactions.tests.factories import InteractionDirectionFactory
from sova.processes.models import ActionFeatureExecution
from sova.processes.tests.factories import ActionInstanceFactory
from sova.workflows.tests.factories import ActionFeatureFactory


class InteractionCompositionFeatureApiTestCase(APITestCase):
    """Features состава взаимодействия добавляют, деактивируют и реактивируют контексты."""

    codes = (
        "interaction_direction.add",
        "interaction_direction.remove",
        "interaction_program.add",
        "interaction_program.remove",
        "interaction_product.add",
        "interaction_product.remove",
    )

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)
        self.action_instance = ActionInstanceFactory()
        self.interaction = self.action_instance.stage_instance.workflow_instance.interaction
        for index, code in enumerate(self.codes, start=200):
            ActionFeatureFactory(
                action=self.action_instance.action,
                code=code,
                sort_order=index,
            )
        self.base_url = f"/api/processes/action-instances/{self.action_instance.pk}/features"

    def execute(self, code: str, payload: dict):
        return self.client.post(
            f"{self.base_url}/{code}/execute/",
            payload,
            format="json",
        )

    def test_adds_and_removes_direction_program_and_product(self) -> None:
        direction = DirectionFactory()
        program = ProgramFactory(direction=direction)
        product = ProductFactory(programs=[program])

        direction_response = self.execute(
            "interaction_direction.add",
            {"direction": str(direction.pk)},
        )
        self.assertEqual(direction_response.status_code, status.HTTP_200_OK, msg=direction_response.data)
        direction_item = InteractionDirection.objects.get(
            interaction=self.interaction,
            direction=direction,
        )

        program_response = self.execute(
            "interaction_program.add",
            {"program": str(program.pk)},
        )
        self.assertEqual(program_response.status_code, status.HTTP_200_OK, msg=program_response.data)
        program_item = InteractionProgram.objects.get(
            interaction=self.interaction,
            program=program,
        )

        product_response = self.execute(
            "interaction_product.add",
            {
                "product": str(product.pk),
                "interaction_program": str(program_item.pk),
            },
        )
        self.assertEqual(product_response.status_code, status.HTTP_200_OK, msg=product_response.data)
        product_item = InteractionProduct.objects.get(
            interaction=self.interaction,
            product=product,
        )
        self.assertEqual(product_item.interaction_program, program_item)

        initial = self.client.get(
            f"{self.base_url}/interaction_product.remove/initial/",
        )
        self.assertEqual(initial.status_code, status.HTTP_200_OK, msg=initial.data)
        self.assertEqual(initial.data["directions"][0]["id"], direction_item.pk)
        self.assertEqual(initial.data["programs"][0]["related_products_count"], 1)
        self.assertEqual(initial.data["products"][0]["id"], product_item.pk)

        for code, payload, item in (
            (
                "interaction_product.remove",
                {"interaction_product": str(product_item.pk)},
                product_item,
            ),
            (
                "interaction_program.remove",
                {"interaction_program": str(program_item.pk)},
                program_item,
            ),
            (
                "interaction_direction.remove",
                {"interaction_direction": str(direction_item.pk)},
                direction_item,
            ),
        ):
            response = self.execute(code, payload)
            self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
            item.refresh_from_db()
            self.assertFalse(item.is_active)

        self.assertEqual(
            list(
                ActionFeatureExecution.objects.order_by("performed_at").values_list(
                    "feature_code_snapshot",
                    flat=True,
                ),
            ),
            list(self.codes[::2]) + list(self.codes[1::2][::-1]),
        )

    def test_add_reactivates_existing_direction(self) -> None:
        item = InteractionDirectionFactory(
            interaction=self.interaction,
            is_active=False,
        )

        response = self.execute(
            "interaction_direction.add",
            {"direction": str(item.direction_id)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        item.refresh_from_db()
        self.assertTrue(item.is_active)
        self.assertEqual(response.data["target"]["id"], item.pk)

    def test_program_requires_its_active_direction(self) -> None:
        program = ProgramFactory()

        response = self.execute(
            "interaction_program.add",
            {"program": str(program.pk)},
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(InteractionProgram.objects.exists())

    def test_product_must_belong_to_selected_program(self) -> None:
        direction_item = InteractionDirectionFactory(interaction=self.interaction)
        program = ProgramFactory(direction=direction_item.direction)
        program_response = self.execute(
            "interaction_program.add",
            {"program": str(program.pk)},
        )
        self.assertEqual(program_response.status_code, status.HTTP_200_OK)
        program_item = InteractionProgram.objects.get(program=program)

        response = self.execute(
            "interaction_product.add",
            {
                "product": str(ProductFactory().pk),
                "interaction_program": str(program_item.pk),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(InteractionProduct.objects.exists())
