from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from sova.catalog.tests.factories import OrganizationFactory, ProgramFactory, B2CClientFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Interaction
from sova.interactions.tests.factories import InteractionFactory, InteractionProgramFactory
from sova.training.enum import TrainingStreamStatus
from sova.training.models import TrainingInstructor, TrainingStreamInstructor
from sova.training.services.stream import training_stream_service
from sova.training.tests.factories import TrainingStreamFactory


class RankingDemoInstructorTest(TestCase):
    def setUp(self):
        UserFactory()

    def run_demo(self):
        call_command("load_training_ranking_demo", stdout=StringIO())

    def test_fresh_demo_creates_five_suitable_instructors_without_duplicates(self):
        OrganizationFactory.create_batch(9, lat="55", lon="37")
        ProgramFactory.create_batch(12)
        self.run_demo()
        self.assertEqual(TrainingInstructor.objects.count(), 5)
        self.assertEqual(TrainingInstructor.objects.filter(organization__isnull=False).count(), 3)
        self.assertEqual(TrainingInstructor.objects.filter(b2c_client__isnull=False).count(), 2)
        links = TrainingStreamInstructor.objects.count()
        self.assertGreaterEqual(links, 5)
        for link in TrainingStreamInstructor.objects.select_related("stream__interaction_program"):
            self.assertTrue(training_stream_service.suitable_instructors(
                link.stream.interaction_program,
            ).filter(pk=link.instructor_id).exists())
        for instructor in TrainingInstructor.objects.all():
            instructor.full_clean()
            self.assertTrue(instructor.directions.exists())
        self.run_demo()
        self.assertEqual(TrainingInstructor.objects.count(), 5)
        self.assertEqual(TrainingStreamInstructor.objects.count(), links)
        self.assertEqual(Interaction.objects.count(), 14)

    def test_existing_demo_is_backfilled_without_assigning_closed_stream(self):
        interaction = InteractionFactory(comment="[ranking-demo] existing")
        program = InteractionProgramFactory(interaction=interaction)
        opened = TrainingStreamFactory(interaction_program=program)
        closed = TrainingStreamFactory(interaction_program=program, status=TrainingStreamStatus.COMPLETED)
        unrelated = TrainingStreamFactory()
        self.run_demo()
        self.assertEqual(TrainingInstructor.objects.count(), 1)
        self.assertEqual(opened.instructors.count(), 1)
        self.assertFalse(closed.instructors.exists())
        self.assertFalse(unrelated.instructors.exists())

    def test_b2c_only_demo_has_valid_employer(self):
        interaction = InteractionFactory(
            organization=None, b2c_client=B2CClientFactory(), comment="[ranking-demo] B2C",
        )
        stream = TrainingStreamFactory(interaction_program=InteractionProgramFactory(interaction=interaction))
        self.run_demo()
        instructor = TrainingInstructor.objects.get()
        self.assertEqual(instructor.b2c_client_id, interaction.b2c_client_id)
        self.assertIsNone(instructor.organization_id)
        self.assertTrue(stream.instructors.filter(pk=instructor.pk).exists())
