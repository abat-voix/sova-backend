import datetime

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import ContractFactory, InteractionFactory, InteractionProgramFactory
from sova.processes.enum import StageInstanceContextType
from sova.processes.models import ActionFeatureExecution
from sova.processes.tests.factories import ActionInstanceFactory
from sova.training.models import TrainingStream
from sova.training.tests.factories import TrainingInstructorFactory
from sova.workflows.tests.factories import ActionFeatureFactory


class CreateTrainingStreamFeatureTestCase(APITestCase):
    """Feature `training.create`: кнопка создания потока у действия после подписания договора."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)
        self.interaction = InteractionFactory()
        self.contract = ContractFactory(interaction=self.interaction, signed_at=datetime.date(2026, 1, 10))
        self.program = InteractionProgramFactory(interaction=self.interaction)
        self.other_program = InteractionProgramFactory(interaction=self.interaction)
        InteractionProgramFactory(interaction=self.interaction, is_active=False)
        self.instructor = TrainingInstructorFactory(university=self.interaction.university)
        TrainingInstructorFactory(university=UniversityFactory())
        self.use_stage()

    def use_stage(self, **stage) -> None:
        self.action_instance = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
            **{f"stage_instance__{key}": value for key, value in stage.items()},
        )
        ActionFeatureFactory(action=self.action_instance.action, code="training.create")
        self.base_url = f"/api/processes/action-instances/{self.action_instance.pk}/features/training.create"

    def test_initial_lists_active_programs_and_counterparty_instructors(self) -> None:
        response = self.client.get(f"{self.base_url}/initial/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(
            {item["id"] for item in response.data["programs"]}, {str(self.program.pk), str(self.other_program.pk)}
        )
        self.assertTrue(response.data["has_signed_contract"])
        self.assertEqual([item["id"] for item in response.data["instructors"]], [str(self.instructor.pk)])

    def test_initial_on_program_stage_offers_only_its_program(self) -> None:
        self.use_stage(context_type=StageInstanceContextType.PROGRAM, context_id=self.program.pk)

        response = self.client.get(f"{self.base_url}/initial/")

        self.assertEqual([item["id"] for item in response.data["programs"]], [str(self.program.pk)])

    def test_execute_creates_stream(self) -> None:
        response = self.client.post(
            f"{self.base_url}/execute/",
            {
                "interaction_program": str(self.program.pk),
                "name": "DevOps-01",
                "starts_at": "2026-02-01",
                "ends_at": "2026-05-01",
                "instructors": [str(self.instructor.pk)],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        stream = TrainingStream.objects.get()
        self.assertEqual((stream.interaction_program, stream.name), (self.program, "DevOps-01"))
        self.assertEqual(list(stream.instructors.all()), [self.instructor])
        execution = ActionFeatureExecution.objects.get()
        self.assertEqual((execution.target_type, execution.target_id), ("training_stream", stream.pk))

    def test_execute_without_signed_contract_is_conflict(self) -> None:
        self.contract.signed_at = None
        self.contract.save()

        response = self.client.post(
            f"{self.base_url}/execute/", {"interaction_program": str(self.program.pk), "name": "1"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "contract_not_signed")
        self.assertFalse(TrainingStream.objects.exists())

    def test_execute_rejects_program_of_another_interaction(self) -> None:
        response = self.client.post(
            f"{self.base_url}/execute/",
            {"interaction_program": str(InteractionProgramFactory().pk), "name": "1"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interaction_program", response.data)

    def test_execute_rejects_foreign_instructor_atomically(self) -> None:
        response = self.client.post(
            f"{self.base_url}/execute/",
            {
                "interaction_program": str(self.program.pk),
                "name": "1",
                "instructors": [str(TrainingInstructorFactory(university=UniversityFactory()).pk)],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "instructor_counterparty_mismatch")
        self.assertFalse(TrainingStream.objects.exists())
