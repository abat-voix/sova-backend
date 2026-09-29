import datetime

from django.test import TestCase

from sova.catalog.tests.factories import B2CClientFactory, OrganizationFactory, ProgramFactory
from sova.interactions.tests.factories import ContractFactory, InteractionFactory, InteractionProgramFactory
from sova.training.enum import TrainingStreamStatus
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
        instructor = TrainingInstructorFactory(
            organization=program.interaction.organization, programs=[program.program]
        )

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
        instructor = TrainingInstructorFactory(
            organization=None, b2c_client=program.interaction.b2c_client, programs=[program.program]
        )

        stream = training_stream_service.create_training_stream(
            interaction_program=program, name="1", instructors=[instructor], user=None
        )

        self.assertEqual(list(stream.instructors.all()), [instructor])


class AssignInstructorTestCase(TestCase):
    def setUp(self) -> None:
        self.stream = TrainingStreamFactory()
        self.organization = self.stream.interaction_program.interaction.organization
        self.program = self.stream.interaction_program.program

    def instructor(self, **kwargs):
        """Преподаватель контрагента, который ведёт программу потока."""
        return TrainingInstructorFactory(**{"organization": self.organization, "programs": [self.program], **kwargs})

    def assert_rejected(self, instructor, code: str) -> None:
        with self.assertRaises(TrainingError) as error:
            training_stream_service.assign_instructor(stream=self.stream, instructor=instructor, user=None)
        self.assertEqual(error.exception.error_code, code)

    def close_stream(self, stream_status: str) -> None:
        self.stream.status = stream_status
        self.stream.save()

    def test_other_organization_rejected(self) -> None:
        self.assert_rejected(self.instructor(organization=OrganizationFactory()), "instructor_counterparty_mismatch")

    def test_instructor_without_stream_program_rejected(self) -> None:
        self.assert_rejected(self.instructor(programs=[ProgramFactory()]), "instructor_program_mismatch")

    def test_repeat_assignment_rejected(self) -> None:
        instructor = self.instructor()
        training_stream_service.assign_instructor(stream=self.stream, instructor=instructor, user=None)

        self.assert_rejected(instructor, "instructor_already_assigned")

    def test_inactive_instructor_rejected(self) -> None:
        self.assert_rejected(self.instructor(is_active=False), "instructor_inactive")

    def test_closed_stream_rejects_assign(self) -> None:
        for stream_status in (TrainingStreamStatus.COMPLETED, TrainingStreamStatus.CANCELLED):
            with self.subTest(stream_status):
                self.close_stream(stream_status)
                self.assert_rejected(self.instructor(), "stream_closed")

    def test_unassign(self) -> None:
        instructor = self.instructor()
        training_stream_service.assign_instructor(stream=self.stream, instructor=instructor, user=None)

        training_stream_service.unassign_instructor(stream=self.stream, instructor=instructor)

        self.assertFalse(self.stream.instructors.exists())

    def test_closed_stream_rejects_unassign(self) -> None:
        instructor = self.instructor()
        training_stream_service.assign_instructor(stream=self.stream, instructor=instructor, user=None)
        self.close_stream(TrainingStreamStatus.COMPLETED)

        with self.assertRaises(TrainingError) as error:
            training_stream_service.unassign_instructor(stream=self.stream, instructor=instructor)
        self.assertEqual(error.exception.error_code, "stream_closed")
        self.assertTrue(self.stream.instructors.exists())


class AssignableInstructorsTestCase(TestCase):
    def setUp(self) -> None:
        self.stream = TrainingStreamFactory()
        self.organization = self.stream.interaction_program.interaction.organization
        self.program = self.stream.interaction_program.program

    def test_only_active_counterparty_instructors_of_stream_program_not_assigned(self) -> None:
        suitable = TrainingInstructorFactory(organization=self.organization, programs=[self.program])
        assigned = TrainingInstructorFactory(organization=self.organization, programs=[self.program])
        training_stream_service.assign_instructor(stream=self.stream, instructor=assigned, user=None)
        TrainingInstructorFactory(organization=self.organization, programs=[ProgramFactory()])
        TrainingInstructorFactory(organization=self.organization)
        TrainingInstructorFactory(organization=self.organization, programs=[self.program], is_active=False)
        TrainingInstructorFactory(organization=OrganizationFactory(), programs=[self.program])

        self.assertEqual(list(training_stream_service.assignable_instructors(self.stream)), [suitable])

    def test_closed_stream_has_no_assignable(self) -> None:
        TrainingInstructorFactory(organization=self.organization, programs=[self.program])
        self.stream.status = TrainingStreamStatus.CANCELLED
        self.stream.save()

        self.assertFalse(training_stream_service.assignable_instructors(self.stream).exists())
