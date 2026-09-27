from django.test import TestCase

from sova.catalog.tests.factories import ProgramFactory
from sova.interactions.tests.factories import InteractionProgramFactory
from sova.training.enum import TrainingApplicationStatus
from sova.training.exceptions import TrainingError
from sova.training.models import TrainingApplicationLearner
from sova.training.services.payment import training_payment_service
from sova.training.tests.factories import (
    LearnerFactory,
    TrainingApplicationLearnerFactory,
    TrainingStreamFactory,
)


class TrainingPaymentServiceTest(TestCase):
    def setUp(self):
        program = ProgramFactory(name="Промпт-инжиниринг")
        self.stream = TrainingStreamFactory(interaction_program=InteractionProgramFactory(program=program))
        self.learner = LearnerFactory(
            last_name="Осипенко", first_name="Ирина", middle_name="Викторовна",
            email="Osipenko833484@mail.ru", phone="79934253846",
        )
        self.participant = TrainingApplicationLearnerFactory(application__stream=self.stream, learner=self.learner)

    def data(self, **overrides):
        return {
            "stream_id": str(self.stream.pk),
            "course": "Промпт-инжиниринг",
            "last_name": "Осипенко",
            "first_name": "Ирина",
            "middle_name": "Викторовна",
            "email": "osipenko833484@mail.ru",
            "phone": "7 (993) 425-38-46",
            **overrides,
        }

    def assert_error(self, code, **overrides):
        with self.assertRaises(TrainingError) as context:
            training_payment_service.register(**self.data(**overrides))
        self.assertEqual(context.exception.error_code, code)
        self.assertFalse(TrainingApplicationLearner.objects.filter(is_paid=True).exists())

    def test_marks_participant_paid_by_name_and_contacts(self):
        participant = training_payment_service.register(**self.data())
        self.assertEqual(participant, self.participant)
        self.participant.refresh_from_db()
        self.assertTrue(self.participant.is_paid)

    def test_phone_alone_is_enough_when_email_is_absent(self):
        training_payment_service.register(**self.data(email=""))
        self.participant.refresh_from_db()
        self.assertTrue(self.participant.is_paid)

    def test_contact_missing_at_learner_is_not_compared(self):
        self.learner.phone = ""
        self.learner.save()
        training_payment_service.register(**self.data())
        self.participant.refresh_from_db()
        self.assertTrue(self.participant.is_paid)

    def test_different_phone_is_not_a_match(self):
        self.assert_error("learner_not_found", phone="7 (900) 000-00-00")

    def test_different_email_is_not_a_match(self):
        self.assert_error("learner_not_found", email="other@mail.ru")

    def test_repeated_payment_is_idempotent(self):
        training_payment_service.register(**self.data())
        self.assertTrue(training_payment_service.register(**self.data()).is_paid)

    def test_unknown_stream(self):
        self.assert_error("stream_not_found", stream_id="1")

    def test_course_must_match_stream_program(self):
        self.assert_error("course_mismatch", course="Инженер-тестировщик")

    def test_contacts_must_match(self):
        self.assert_error("learner_not_found", email="other@mail.ru", phone="70000000000")

    def test_name_must_match(self):
        self.assert_error("learner_not_found", first_name="Мария")

    def test_learner_without_stream_application(self):
        self.participant.delete()
        self.assert_error("learner_not_in_stream")

    def test_cancelled_application_is_not_paid(self):
        self.participant.application.status = TrainingApplicationStatus.CANCELLED
        self.participant.application.save(update_fields=["status"])
        self.assert_error("learner_not_in_stream")

    def test_ambiguous_learner(self):
        twin = LearnerFactory(
            last_name="Осипенко", first_name="Ирина", middle_name="Викторовна",
            email="osipenko833484@mail.ru", phone="79934253846",
        )
        TrainingApplicationLearnerFactory(application__stream=self.stream, learner=twin)
        self.assert_error("learner_ambiguous")
