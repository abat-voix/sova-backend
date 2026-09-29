import datetime
from io import StringIO

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings

from sova.catalog.tests.factories import B2CClientFactory, OrganizationFactory
from sova.core.crypto import blind_index, decrypt
from sova.training.models import Learner, LearnerPersonalData, TrainingInstructor
from sova.training.tests.factories import (
    LearnerFactory,
    LearnerPersonalDataFactory,
    TrainingApplicationFactory,
    TrainingApplicationLearnerFactory,
    TrainingInstructorFactory,
    TrainingInstructorQualificationFactory,
    TrainingStreamFactory,
)


def raw_row(model, pk) -> str:
    """Строка таблицы модели как её видит БД — всё, что там лежит, одной строкой."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {model._meta.db_table} WHERE id = %s", [pk.hex])
        row = cursor.fetchone()
        if row is None:
            cursor.execute(f"SELECT * FROM {model._meta.db_table} WHERE id = %s", [str(pk)])
            row = cursor.fetchone()
    return " ".join(str(value) for value in row)


class TrainingStreamModelTestCase(TestCase):
    def test_program_can_have_several_streams(self) -> None:
        first = TrainingStreamFactory()
        TrainingStreamFactory(interaction_program=first.interaction_program)

        self.assertEqual(first.interaction_program.streams.count(), 2)

    def test_end_before_start_is_rejected(self) -> None:
        with self.assertRaises(IntegrityError):
            TrainingStreamFactory(starts_at=datetime.date(2026, 3, 1), ends_at=datetime.date(2026, 2, 1))


class TrainingInstructorModelTestCase(TestCase):
    def test_exactly_one_organization(self) -> None:
        TrainingInstructorFactory(organization=None, b2c_client=B2CClientFactory())
        with transaction.atomic(), self.assertRaises(IntegrityError):
            TrainingInstructorFactory(organization=None, b2c_client=None)
        with self.assertRaises(IntegrityError):
            TrainingInstructorFactory(organization=OrganizationFactory(), b2c_client=B2CClientFactory())

    def test_lms_id_unique_only_when_filled(self) -> None:
        TrainingInstructorFactory()
        TrainingInstructorFactory()
        TrainingInstructorFactory(lms_external_id="lms-1")
        with self.assertRaises(IntegrityError):
            TrainingInstructorFactory(lms_external_id="lms-1")

    def test_several_qualifications(self) -> None:
        instructor = TrainingInstructorFactory()
        TrainingInstructorQualificationFactory(instructor=instructor)
        TrainingInstructorQualificationFactory(instructor=instructor)

        self.assertEqual(instructor.qualifications.count(), 2)

    def test_stream_instructor_pair_is_unique(self) -> None:
        stream = TrainingStreamFactory()
        instructor = TrainingInstructorFactory()
        stream.instructors.add(instructor)
        stream.instructors.add(instructor)

        self.assertEqual(stream.instructor_links.count(), 1)
        self.assertIsInstance(stream.instructors.get(), TrainingInstructor)


class TrainingApplicationModelTestCase(TestCase):
    def test_stream_is_required(self) -> None:
        with self.assertRaises(IntegrityError):
            TrainingApplicationFactory(stream=None)

    def test_learner_once_per_application(self) -> None:
        participant = TrainingApplicationLearnerFactory()
        with self.assertRaises(IntegrityError):
            TrainingApplicationLearnerFactory(application=participant.application, learner=participant.learner)


class LearnerModelTestCase(TestCase):
    def test_contacts_are_encrypted_and_indexed(self) -> None:
        learner = LearnerFactory(email=" Cherepanona.S@test.ru ", phone="7 (999) 023-43-65")

        row = raw_row(Learner, learner.pk)
        self.assertNotIn("cherepanona", row.lower())
        self.assertNotIn("0234365", row)
        learner.refresh_from_db()
        self.assertEqual(learner.email, "cherepanona.s@test.ru")
        self.assertEqual(learner.phone, "79990234365")
        self.assertEqual(learner.email_hash, blind_index("cherepanona.s@test.ru"))
        self.assertEqual(learner.phone_hash, blind_index("79990234365"))

    def test_personal_data_is_encrypted(self) -> None:
        data = LearnerPersonalDataFactory(
            snils="123-456-789 45",
            passport_number="567890",
            birth_date=datetime.date(2000, 5, 17),
            last_name_dative="Иванову",
        )

        row = raw_row(LearnerPersonalData, data.pk)
        self.assertNotIn("567890", row)
        self.assertNotIn("2000-05-17", row)
        self.assertIn("Иванову", row)
        data.refresh_from_db()
        self.assertEqual(data.birth_date, datetime.date(2000, 5, 17))
        self.assertEqual(data.snils_hash, blind_index("12345678945"))


class RotatePdKeysCommandTestCase(TestCase):
    def test_rotation_reencrypts_with_current_key(self) -> None:
        old_key, new_key = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        with override_settings(PD_ENCRYPTION_KEYS=[old_key]):
            learner = LearnerFactory(email="rotate@test.ru")
            LearnerPersonalDataFactory(learner=learner, snils="123-456-789 45")
        with override_settings(PD_ENCRYPTION_KEYS=[new_key, old_key]):
            call_command("rotate_pd_keys", stdout=StringIO())
        with override_settings(PD_ENCRYPTION_KEYS=[new_key]):
            learner = Learner.objects.get(pk=learner.pk)
            self.assertEqual(learner.email, "rotate@test.ru")
            self.assertEqual(learner.personal_data.snils, "123-456-789 45")
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT email FROM {Learner._meta.db_table}")
                (token,) = cursor.fetchone()
            self.assertEqual(decrypt(token), "rotate@test.ru")
