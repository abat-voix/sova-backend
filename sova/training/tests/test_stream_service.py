import datetime

from django.test import TestCase

from sova.catalog.tests.factories import B2CClientFactory, OrganizationFactory
from sova.interactions.tests.factories import ContractFactory, InteractionFactory, InteractionProgramFactory
from sova.training.exceptions import TrainingError
from sova.training.services.stream import training_stream_service
from sova.training.tests.factories import TrainingInstructorFactory, TrainingStreamFactory


def signed_program(**interaction_kwargs):
    """Активная программа взаимодействия с подписанным договором."""
    interaction = InteractionFactory(**interaction_kwargs)
    ContractFactory(interaction=interaction, signed_at=datetime.date(2026, 1, 10))
    return InteractionProgramFactory(interaction=interaction)


class CreateTrainingStreamTestCase(TestCase):
    def test_creates_stream_with_instructors(self) -> None:
        program = signed_program()
        instructor = TrainingInstructorFactory(organization=program.interaction.organization)

        stream = training_stream_service.create_training_stream(
            interaction_program=program,
            name="DevOps-01",
            instructors=[instructor],
            user=None,
        )

        self.assertEqual(stream.interaction_program, program)
        self.assertEqual(list(stream.instructors.all()), [instructor])

    def test_several_streams_per_program(self) -> None:
        program = signed_program()
        training_stream_service.create_training_stream(interaction_program=program, name="1", user=None)
        training_stream_service.create_training_stream(interaction_program=program, name="2", user=None)

        self.assertEqual(program.streams.count(), 2)

    def test_requires_signed_contract(self) -> None:
        program = InteractionProgramFactory()
        ContractFactory(interaction=program.interaction, signed_at=None)

        with self.assertRaises(TrainingError) as error:
            training_stream_service.create_training_stream(interaction_program=program, name="1", user=None)
        self.assertEqual(error.exception.error_code, "contract_not_signed")

    def test_requires_active_program(self) -> None:
        program = signed_program()
        program.is_active = False
        program.save()

        with self.assertRaises(TrainingError) as error:
            training_stream_service.create_training_stream(interaction_program=program, name="1", user=None)
        self.assertEqual(error.exception.error_code, "program_inactive")

    def test_b2c_interaction_allowed(self) -> None:
        program = signed_program(organization=None, b2c_client=B2CClientFactory())
        instructor = TrainingInstructorFactory(organization=None, b2c_client=program.interaction.b2c_client)

        stream = training_stream_service.create_training_stream(
            interaction_program=program, name="1", instructors=[instructor], user=None
        )

        self.assertEqual(list(stream.instructors.all()), [instructor])


class AssignInstructorTestCase(TestCase):
    def setUp(self) -> None:
        self.stream = TrainingStreamFactory()
        self.organization = self.stream.interaction_program.interaction.organization

    def test_other_organization_rejected(self) -> None:
        with self.assertRaises(TrainingError) as error:
            training_stream_service.assign_instructor(
                stream=self.stream, instructor=TrainingInstructorFactory(organization=OrganizationFactory()), user=None
            )
        self.assertEqual(error.exception.error_code, "instructor_counterparty_mismatch")

    def test_repeat_assignment_rejected(self) -> None:
        instructor = TrainingInstructorFactory(organization=self.organization)
        training_stream_service.assign_instructor(stream=self.stream, instructor=instructor, user=None)

        with self.assertRaises(TrainingError) as error:
            training_stream_service.assign_instructor(stream=self.stream, instructor=instructor, user=None)
        self.assertEqual(error.exception.error_code, "instructor_already_assigned")

    def test_inactive_instructor_rejected(self) -> None:
        instructor = TrainingInstructorFactory(organization=self.organization, is_active=False)

        with self.assertRaises(TrainingError) as error:
            training_stream_service.assign_instructor(stream=self.stream, instructor=instructor, user=None)
        self.assertEqual(error.exception.error_code, "instructor_inactive")

    def test_unassign(self) -> None:
        instructor = TrainingInstructorFactory(organization=self.organization)
        training_stream_service.assign_instructor(stream=self.stream, instructor=instructor, user=None)

        training_stream_service.unassign_instructor(stream=self.stream, instructor=instructor)

        self.assertFalse(self.stream.instructors.exists())
