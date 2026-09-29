from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from accounts.policy import Action, can
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory, InteractionProgramFactory
from sova.training.enum import PersonalDataAccessAction, TrainingApplicationStatus
from sova.training.models import (
    Learner,
    LearnerPersonalData,
    LearnerPersonalDataAccessLog,
    TrainingApplication,
)
from sova.training.tests.factories import TrainingStreamFactory

BASE = "/api/training"


def user_with_role(role: str):
    user = UserFactory()
    UserRole.objects.update_or_create(user=user, defaults={"role": role})
    return user


class LearnerRightsTestCase(APITestCase):
    def test_working_roles_read_and_update_personal_data(self) -> None:
        """КАМ, руководитель и админ читают и правят ПД; наблюдатель — нет."""
        for role in (SystemRole.KAM, SystemRole.HEAD, SystemRole.PLATFORM_ADMIN):
            user = user_with_role(role)
            with self.subTest(role=role):
                self.assertTrue(can(user, Action.TRAINING_PERSONAL_DATA_READ))
                self.assertTrue(can(user, Action.TRAINING_PERSONAL_DATA_UPDATE))
        observer = user_with_role(SystemRole.OBSERVER)
        self.assertFalse(can(observer, Action.TRAINING_PERSONAL_DATA_READ))
        self.assertFalse(can(observer, Action.TRAINING_PERSONAL_DATA_UPDATE))

    def test_kam_reads_personal_data_of_any_learner_with_log(self) -> None:
        """КАМ открывает ПД любого обучающегося, просмотр пишется в журнал."""
        self.client.force_authenticate(user_with_role(SystemRole.KAM))
        learner = Learner.objects.create(last_name="Иванов", first_name="Иван", email="ivan@example.com")

        response = self.client.get(f"{BASE}/learners/{learner.pk}/personal-data/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["email"], "ivan@example.com")
        self.assertEqual(LearnerPersonalDataAccessLog.objects.get().action, PersonalDataAccessAction.READ)


class LearnerCardTestCase(APITestCase):
    def setUp(self) -> None:
        self.client.force_authenticate(user_with_role(SystemRole.KAM))

    def test_kam_creates_learner_without_consent(self) -> None:
        response = self.client.post(
            f"{BASE}/learners/",
            {"last_name": "Иванов", "first_name": "Иван", "phone": "+7 999 123-45-67"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        learner = Learner.objects.get()
        self.assertEqual(learner.phone, "79991234567")
        self.assertIsNone(learner.consent_at)
        # Ответ — как список: контакты замаскированы
        self.assertNotEqual(response.data["phone"], "79991234567")

    def test_contact_required(self) -> None:
        response = self.client.post(f"{BASE}/learners/", {"last_name": "Иванов", "first_name": "Иван"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Learner.objects.exists())

    def test_duplicate_contacts_return_existing_learner(self) -> None:
        existing = Learner.objects.create(last_name="Петров", first_name="Пётр", email="petr@example.com")

        response = self.client.post(
            f"{BASE}/learners/",
            {"last_name": "Петров", "first_name": "Пётр", "email": "PETR@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "learner_exists")
        self.assertEqual(str(response.data["learner"]), str(existing.pk))
        self.assertEqual(Learner.objects.count(), 1)

    def test_update_to_foreign_contact_is_rejected(self) -> None:
        Learner.objects.create(last_name="Петров", first_name="Пётр", email="petr@example.com")
        learner = Learner.objects.create(last_name="Иванов", first_name="Иван", email="ivan@example.com")

        response = self.client.patch(f"{BASE}/learners/{learner.pk}/", {"email": "petr@example.com"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        learner.refresh_from_db()
        self.assertEqual(learner.email, "ivan@example.com")

    def test_update_keeps_own_contact(self) -> None:
        """Свой же контакт при правке — не дубль."""
        learner = Learner.objects.create(last_name="Иванов", first_name="Иван", email="ivan@example.com")

        response = self.client.patch(
            f"{BASE}/learners/{learner.pk}/", {"middle_name": "Иванович", "email": "ivan@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)

    def test_update_cannot_clear_last_contact(self) -> None:
        learner = Learner.objects.create(last_name="Иванов", first_name="Иван", email="ivan@example.com")

        response = self.client.patch(f"{BASE}/learners/{learner.pk}/", {"email": ""}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deactivate_instead_of_delete(self) -> None:
        learner = Learner.objects.create(last_name="Иванов", first_name="Иван", email="ivan@example.com")

        patched = self.client.patch(f"{BASE}/learners/{learner.pk}/", {"is_active": False}, format="json")
        deleted = self.client.delete(f"{BASE}/learners/{learner.pk}/")

        self.assertEqual(patched.status_code, status.HTTP_200_OK, msg=patched.data)
        # Права проверяются раньше метода: удаления нет ни в правах, ни в методах
        self.assertIn(deleted.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED))
        self.assertTrue(Learner.objects.filter(pk=learner.pk, is_active=False).exists())

    def test_observer_cannot_create(self) -> None:
        self.client.force_authenticate(user_with_role(SystemRole.OBSERVER))

        response = self.client.post(
            f"{BASE}/learners/", {"last_name": "Иванов", "first_name": "Иван", "email": "i@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class LearnerPersonalDataEditTestCase(APITestCase):
    def setUp(self) -> None:
        self.user = user_with_role(SystemRole.HEAD)
        self.client.force_authenticate(self.user)
        self.learner = Learner.objects.create(last_name="Иванов", first_name="Иван", email="ivan@example.com")
        self.url = f"{BASE}/learners/{self.learner.pk}/personal-data/"

    def test_head_creates_missing_personal_data_and_logs_update(self) -> None:
        response = self.client.patch(
            self.url,
            {"snils": "123-456-789 45", "birth_date": "1990-05-01", "gender": "male"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        data = LearnerPersonalData.objects.get(learner=self.learner)
        self.assertEqual(str(data.birth_date), "1990-05-01")
        self.assertTrue(data.snils_hash)
        log = LearnerPersonalDataAccessLog.objects.get(action=PersonalDataAccessAction.UPDATE)
        self.assertEqual(sorted(log.fields), ["birth_date", "gender", "snils"])
        self.assertEqual(log.user, self.user)

    def test_update_response_disclosure_is_logged_as_read(self) -> None:
        """Ответ PATCH содержит все ПД — их выдача пишется в журнал как просмотр, а не только правка."""
        LearnerPersonalData.objects.create(learner=self.learner, passport_series="4510")

        response = self.client.patch(self.url, {"gender": "male"}, format="json")

        self.assertEqual(response.data["passport_series"], "4510")
        actions = sorted(LearnerPersonalDataAccessLog.objects.values_list("action", flat=True))
        self.assertEqual(actions, [PersonalDataAccessAction.READ, PersonalDataAccessAction.UPDATE])

    def test_update_changes_only_sent_fields(self) -> None:
        LearnerPersonalData.objects.create(learner=self.learner, passport_series="4510", gender="male")

        response = self.client.patch(self.url, {"passport_number": "123456"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        data = LearnerPersonalData.objects.get(learner=self.learner)
        self.assertEqual((data.passport_series, data.passport_number, data.gender), ("4510", "123456", "male"))

    def test_observer_cannot_update(self) -> None:
        self.client.force_authenticate(user_with_role(SystemRole.OBSERVER))

        response = self.client.patch(self.url, {"gender": "male"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(LearnerPersonalData.objects.exists())

    def test_invalid_choice_is_rejected(self) -> None:
        response = self.client.patch(self.url, {"education_level": "phd"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class NewLearnerFromApplicationTestCase(APITestCase):
    def setUp(self) -> None:
        self.kam = user_with_role(SystemRole.KAM)
        self.client.force_authenticate(self.kam)
        interaction = InteractionFactory()
        responsible_service.assign(interaction=interaction, manager=self.kam, assigned_by=None)
        stream = TrainingStreamFactory(interaction_program=InteractionProgramFactory(interaction=interaction))
        self.application = TrainingApplication.objects.create(stream=stream)
        self.url = f"{BASE}/application-learners/"

    def post_new(self, **learner):
        fields = {"last_name": "Иванов", "first_name": "Иван", "email": "ivan@example.com", **learner}
        return self.client.post(
            self.url, {"application": str(self.application.pk), "new_learner": fields}, format="json"
        )

    def test_new_learner_is_created_and_added(self) -> None:
        response = self.post_new()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(self.application.participants.get().learner.email, "ivan@example.com")

    def test_existing_contact_returns_learner_exists(self) -> None:
        existing = Learner.objects.create(last_name="Иванов", first_name="Иван", email="ivan@example.com")

        response = self.post_new(first_name="И.")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(str(response.data["learner"]), str(existing.pk))
        self.assertFalse(self.application.participants.exists())

    def test_cancelled_application_rolls_back_new_learner(self) -> None:
        self.application.status = TrainingApplicationStatus.CANCELLED
        self.application.save()

        response = self.post_new()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(Learner.objects.exists())

    def test_exactly_one_of_learner_and_new_learner(self) -> None:
        learner = Learner.objects.create(last_name="Петров", first_name="Пётр", email="petr@example.com")

        both = self.client.post(
            self.url,
            {
                "application": str(self.application.pk),
                "learner": str(learner.pk),
                "new_learner": {"last_name": "Иванов", "first_name": "Иван", "email": "ivan@example.com"},
            },
            format="json",
        )
        neither = self.client.post(self.url, {"application": str(self.application.pk)}, format="json")

        self.assertEqual(both.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(neither.status_code, status.HTTP_400_BAD_REQUEST)
