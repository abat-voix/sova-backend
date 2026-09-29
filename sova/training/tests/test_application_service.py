from django.test import TestCase

from sova.training.enum import TrainingApplicationStatus, TrainingStreamStatus
from sova.training.exceptions import TrainingError
from sova.training.models import TrainingApplication
from sova.training.services.application import training_application_service
from sova.training.services.enrollment import training_enrollment_service
from sova.training.tests.factories import (
    LearnerFactory,
    TrainingApplicationFactory,
    TrainingApplicationLearnerFactory,
    TrainingStreamFactory,
)


class TrainingApplicationServiceTestCase(TestCase):
    def setUp(self) -> None:
        self.stream = TrainingStreamFactory()

    def test_create_with_several_learners(self) -> None:
        first, second = LearnerFactory(), LearnerFactory()

        application = training_application_service.create_application(
            stream=self.stream, learners=[first, second], user=None, comment="Группа 1"
        )

        self.assertEqual(set(application.learners.all()), {first, second})
        self.assertEqual(application.status, TrainingApplicationStatus.NEW)
        self.assertEqual(application.comment, "Группа 1")

    def test_repeat_learner_in_request_rejected(self) -> None:
        learner = LearnerFactory()

        with self.assertRaises(TrainingError) as error:
            training_application_service.create_application(stream=self.stream, learners=[learner, learner], user=None)
        self.assertEqual(error.exception.error_code, "learner_already_in_application")

    def test_cancelled_stream_rejected(self) -> None:
        self.stream.status = TrainingStreamStatus.CANCELLED
        self.stream.save()

        with self.assertRaises(TrainingError) as error:
            training_application_service.create_application(stream=self.stream, learners=[LearnerFactory()], user=None)
        self.assertEqual(error.exception.error_code, "stream_cancelled")

    def test_same_learner_reuses_card_across_applications(self) -> None:
        learner = LearnerFactory()
        training_application_service.create_application(stream=self.stream, learners=[learner], user=None)
        training_application_service.create_application(stream=TrainingStreamFactory(), learners=[learner], user=None)

        self.assertEqual(learner.applications.count(), 2)

    def test_add_and_remove_learner(self) -> None:
        application = training_application_service.create_application(stream=self.stream, learners=[], user=None)
        learner = LearnerFactory()

        training_application_service.add_learner(application=application, learner=learner)
        with self.assertRaises(TrainingError):
            training_application_service.add_learner(application=application, learner=learner)
        training_application_service.remove_learner(application=application, learner=learner)

        self.assertFalse(application.participants.exists())

    def test_paid_learner_cannot_be_removed(self) -> None:
        participant = TrainingApplicationLearnerFactory(application__stream=self.stream, is_paid=True)

        with self.assertRaises(TrainingError) as error:
            training_application_service.remove_learner(application=participant.application, learner=participant.learner)
        self.assertEqual(error.exception.error_code, "learner_paid")

    def test_application_with_paid_learner_cannot_be_deleted(self) -> None:
        participant = TrainingApplicationLearnerFactory(application__stream=self.stream, is_paid=True)

        with self.assertRaises(TrainingError) as error:
            training_application_service.delete_application(participant.application)
        self.assertEqual(error.exception.error_code, "application_has_paid_learners")

    def test_delete_without_payment(self) -> None:
        application = TrainingApplicationLearnerFactory(application__stream=self.stream).application

        training_application_service.delete_application(application)

        self.assertFalse(TrainingApplication.objects.exists())


class PaymentFactTestCase(TestCase):
    """Оплата — только факт у участника заявки: оплачен — зачислен."""

    def setUp(self) -> None:
        self.participant = TrainingApplicationLearnerFactory()

    def test_not_paid_by_default(self) -> None:
        self.assertFalse(self.participant.is_paid)
        self.assertFalse(training_enrollment_service.is_enrolled(self.participant))

    def test_mark_paid_enrolls(self) -> None:
        training_application_service.set_paid(participant=self.participant, is_paid=True)

        self.participant.refresh_from_db()
        self.assertTrue(self.participant.is_paid)
        self.assertTrue(training_enrollment_service.is_enrolled(self.participant))

    def test_unmark_paid(self) -> None:
        training_application_service.set_paid(participant=self.participant, is_paid=True)
        training_application_service.set_paid(participant=self.participant, is_paid=False)

        self.assertFalse(training_enrollment_service.is_enrolled(self.participant))

    def test_group_application_paid_partially(self) -> None:
        other = TrainingApplicationLearnerFactory(application=self.participant.application)

        training_application_service.set_paid(participant=self.participant, is_paid=True)

        self.assertEqual(list(training_enrollment_service.enrolled_participants()), [self.participant])
        self.assertFalse(training_enrollment_service.is_enrolled(other))

    def test_cancelled_application_enrolls_nobody(self) -> None:
        participant = TrainingApplicationLearnerFactory(is_paid=True)
        training_application_service.cancel(participant.application)

        self.assertFalse(training_enrollment_service.is_enrolled(participant))
