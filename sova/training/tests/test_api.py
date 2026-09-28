from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import ProgramFactory, OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory, InteractionProgramFactory
from sova.training.enum import TrainingApplicationStatus
from sova.training.models import (
    LearnerPersonalDataAccessLog,
    TrainingInstructor,
)
from sova.training.tests.factories import (
    LearnerFactory,
    LearnerPersonalDataFactory,
    TrainingApplicationFactory,
    TrainingApplicationLearnerFactory,
    TrainingInstructorFactory,
    TrainingStreamFactory,
)

BASE = "/api/training"


def create_user(role: str) -> object:
    user = UserFactory()
    UserRole.objects.create(user=user, role=role)
    return user


class TrainingApiTestCase(APITestCase):
    def setUp(self) -> None:
        self.kam = create_user(SystemRole.KAM)
        self.admin = create_user(SystemRole.PLATFORM_ADMIN)
        self.interaction = InteractionFactory()
        responsible_service.assign(interaction=self.interaction, manager=self.kam, assigned_by=None)
        self.stream = TrainingStreamFactory(interaction_program=InteractionProgramFactory(interaction=self.interaction))
        foreign = InteractionFactory()
        responsible_service.assign(interaction=foreign, manager=create_user(SystemRole.KAM), assigned_by=None)
        self.foreign_stream = TrainingStreamFactory(interaction_program=InteractionProgramFactory(interaction=foreign))
        self.client.force_authenticate(self.kam)

    def ids(self, response) -> set[str]:
        return {item["id"] for item in response.data["results"]}


class StreamApiTestCase(TrainingApiTestCase):
    def test_kam_sees_streams_of_own_interactions(self) -> None:
        response = self.client.get(f"{BASE}/streams/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids(response), {str(self.stream.pk)})

    def test_counts_participants_and_paid(self) -> None:
        application = TrainingApplicationFactory(stream=self.stream)
        TrainingApplicationLearnerFactory(application=application, is_paid=True)
        TrainingApplicationLearnerFactory(application=application)
        cancelled = TrainingApplicationFactory(stream=self.stream, status=TrainingApplicationStatus.CANCELLED)
        TrainingApplicationLearnerFactory(application=cancelled, is_paid=True)

        response = self.client.get(f"{BASE}/streams/{self.stream.pk}/")

        self.assertEqual(response.data["applications_count"], 2)
        self.assertEqual((response.data["participants_count"], response.data["paid_count"]), (2, 1))

    def test_shows_counterparty_and_interaction_number(self) -> None:
        response = self.client.get(f"{BASE}/streams/{self.stream.pk}/")

        organization = self.interaction.organization
        self.assertEqual((response.data["organization"], response.data["b2c_client"]), (str(organization.pk), None))
        self.assertEqual(response.data["counterparty_name"], organization.name)
        self.assertEqual(response.data["interaction_number"], self.interaction.display_number)

    def test_filter_by_interaction(self) -> None:
        response = self.client.get(f"{BASE}/streams/", {"interaction__ids": str(self.interaction.pk)})

        self.assertEqual(self.ids(response), {str(self.stream.pk)})

    def test_create_only_through_action_feature(self) -> None:
        response = self.client.post(f"{BASE}/streams/", {"name": "x"})

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_patch_stream(self) -> None:
        response = self.client.patch(f"{BASE}/streams/{self.stream.pk}/", {"name": "Новое"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["name"], "Новое")

    def test_assign_and_unassign_instructor(self) -> None:
        instructor = TrainingInstructorFactory(organization=self.interaction.organization)
        url = f"{BASE}/streams/{self.stream.pk}/instructors/"

        assigned = self.client.post(url, {"instructor": str(instructor.pk)}, format="json")
        foreign = self.client.post(
            url, {"instructor": str(TrainingInstructorFactory(organization=OrganizationFactory()).pk)}, format="json"
        )
        removed = self.client.delete(f"{url}{instructor.pk}/")

        self.assertEqual(assigned.status_code, status.HTTP_200_OK, msg=assigned.data)
        self.assertEqual(foreign.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(foreign.data["code"], "instructor_counterparty_mismatch")
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(self.stream.instructors.exists())

    def test_unassign_with_invalid_id_is_not_found(self) -> None:
        response = self.client.delete(f"{BASE}/streams/{self.stream.pk}/instructors/not-a-uuid/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ApplicationApiTestCase(TrainingApiTestCase):
    """Заявка создаётся вручную по видимому потоку (или загрузкой «Пользователей» с потоком)."""

    def test_create_by_stream(self) -> None:
        response = self.client.post(
            f"{BASE}/applications/", {"stream": str(self.stream.pk), "comment": "Группа 1"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual((response.data["stream"], response.data["comment"]), (self.stream.pk, "Группа 1"))
        self.assertEqual(response.data["status"], TrainingApplicationStatus.NEW)

    def test_foreign_stream_rejected(self) -> None:
        response = self.client.post(f"{BASE}/applications/", {"stream": str(self.foreign_stream.pk)}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stream", response.data)

    def test_kam_sees_applications_of_own_streams(self) -> None:
        own = TrainingApplicationFactory(stream=self.stream)
        TrainingApplicationFactory(stream=self.foreign_stream)

        response = self.client.get(f"{BASE}/applications/")

        self.assertEqual(self.ids(response), {str(own.pk)})

    def test_participants_show_enrollment(self) -> None:
        participant = TrainingApplicationLearnerFactory(application__stream=self.stream, is_paid=True)

        response = self.client.get(f"{BASE}/applications/{participant.application.pk}/")

        self.assertTrue(response.data["participants"][0]["is_paid"])
        self.assertTrue(response.data["participants"][0]["is_enrolled"])

    def test_patch_comment_only(self) -> None:
        application = TrainingApplicationFactory(stream=self.stream)

        response = self.client.patch(
            f"{BASE}/applications/{application.pk}/",
            {"comment": "уточнено", "stream": str(TrainingStreamFactory().pk)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual((response.data["comment"], response.data["stream"]), ("уточнено", self.stream.pk))

    def test_cancel(self) -> None:
        application = TrainingApplicationFactory(stream=self.stream)

        response = self.client.post(f"{BASE}/applications/{application.pk}/cancel/")

        self.assertEqual(response.data["status"], TrainingApplicationStatus.CANCELLED)

    def test_delete_only_without_paid_participants(self) -> None:
        paid = TrainingApplicationLearnerFactory(application__stream=self.stream, is_paid=True).application
        free = TrainingApplicationFactory(stream=self.stream)

        conflict = self.client.delete(f"{BASE}/applications/{paid.pk}/")
        deleted = self.client.delete(f"{BASE}/applications/{free.pk}/")

        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(conflict.data["code"], "application_has_paid_learners")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

    def test_no_review_actions(self) -> None:
        application = TrainingApplicationFactory(stream=self.stream)

        for name in ("resolve", "reject"):
            response = self.client.post(f"{BASE}/applications/{application.pk}/{name}/")
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, name)

    def test_observer_reads_but_cannot_write(self) -> None:
        self.client.force_authenticate(create_user(SystemRole.OBSERVER))

        listed = self.client.get(f"{BASE}/applications/")
        created = self.client.post(f"{BASE}/applications/", {"stream": str(self.stream.pk)}, format="json")

        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(created.status_code, status.HTTP_403_FORBIDDEN)


class ApplicationLearnerApiTestCase(TrainingApiTestCase):
    """Участник заявки вручную — чтобы отметить оплату без загрузки JSON."""

    url = f"{BASE}/application-learners/"

    def setUp(self) -> None:
        super().setUp()
        self.application = TrainingApplicationFactory(stream=self.stream)
        self.learner = LearnerFactory()

    def test_create_paid_participant(self) -> None:
        response = self.client.post(
            self.url,
            {"application": str(self.application.pk), "learner": str(self.learner.pk), "is_paid": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertTrue(response.data["is_paid"])
        self.assertTrue(response.data["is_enrolled"])

    def test_duplicate_participant_is_conflict(self) -> None:
        TrainingApplicationLearnerFactory(application=self.application, learner=self.learner)

        response = self.client.post(
            self.url, {"application": str(self.application.pk), "learner": str(self.learner.pk)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "learner_already_in_application")

    def test_foreign_application_rejected(self) -> None:
        foreign = TrainingApplicationFactory(stream=self.foreign_stream)

        response = self.client.post(
            self.url, {"application": str(foreign.pk), "learner": str(self.learner.pk)}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("application", response.data)

    def test_toggle_paid(self) -> None:
        participant = TrainingApplicationLearnerFactory(application=self.application)

        paid = self.client.patch(f"{self.url}{participant.pk}/", {"is_paid": True}, format="json")
        unpaid = self.client.patch(f"{self.url}{participant.pk}/", {"is_paid": False}, format="json")

        self.assertTrue(paid.data["is_paid"])
        self.assertFalse(unpaid.data["is_paid"])

    def test_paid_participant_cannot_be_deleted(self) -> None:
        paid = TrainingApplicationLearnerFactory(application=self.application, is_paid=True)
        free = TrainingApplicationLearnerFactory(application=self.application)

        conflict = self.client.delete(f"{self.url}{paid.pk}/")
        deleted = self.client.delete(f"{self.url}{free.pk}/")

        self.assertEqual(conflict.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(conflict.data["code"], "learner_paid")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

    def test_list_filtered_by_application(self) -> None:
        own = TrainingApplicationLearnerFactory(application=self.application)
        TrainingApplicationLearnerFactory(application=TrainingApplicationFactory(stream=self.stream))
        TrainingApplicationLearnerFactory(application=TrainingApplicationFactory(stream=self.foreign_stream))

        response = self.client.get(self.url, {"application__ids": str(self.application.pk)})

        self.assertEqual(self.ids(response), {str(own.pk)})


class PaymentApiTestCase(TrainingApiTestCase):
    def test_no_payments_endpoint(self) -> None:
        self.assertEqual(self.client.get(f"{BASE}/payments/").status_code, status.HTTP_404_NOT_FOUND)


class LearnerApiTestCase(TrainingApiTestCase):
    """Обучающиеся приходят только из файлов: в API — просмотр с масками, полные ПД — администратору."""

    def setUp(self) -> None:
        super().setUp()
        self.learner = LearnerFactory(email="cherepanona.s@test.ru", phone="79990234365")
        self.data = LearnerPersonalDataFactory(learner=self.learner, snils="123-456-789 45")

    def test_list_masks_contacts(self) -> None:
        response = self.client.get(f"{BASE}/learners/")

        item = next(item for item in response.data["results"] if item["id"] == str(self.learner.pk))
        self.assertEqual(item["email"], "c***@test.ru")
        self.assertEqual(item["phone"], "+7 *** ***-**-65")
        self.assertNotIn("personal_data", item)

    def test_participation_shows_enrollment(self) -> None:
        TrainingApplicationLearnerFactory(application__stream=self.stream, learner=self.learner, is_paid=True)

        response = self.client.get(f"{BASE}/learners/{self.learner.pk}/")

        self.assertTrue(response.data["participations"][0]["is_paid"])
        self.assertTrue(response.data["participations"][0]["is_enrolled"])

    def test_no_manual_creation_or_editing(self) -> None:
        self.client.force_authenticate(self.admin)
        url = f"{BASE}/learners/{self.learner.pk}/"

        created = self.client.post(f"{BASE}/learners/", {"last_name": "Иванов", "first_name": "Иван"})
        updated = self.client.patch(url, {"last_name": "Петров"}, format="json")
        personal = self.client.patch(f"{url}personal-data/", {"passport_series": "4510"}, format="json")

        for response in (created, updated, personal):
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_personal_data_only_for_platform_admin(self) -> None:
        url = f"{BASE}/learners/{self.learner.pk}/personal-data/"

        denied = self.client.get(url)
        self.client.force_authenticate(self.admin)
        allowed = self.client.get(url)

        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(allowed.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed.data["snils"], "123-456-789 45")
        self.assertEqual(allowed.data["email"], "cherepanona.s@test.ru")
        self.assertEqual(LearnerPersonalDataAccessLog.objects.get().user, self.admin)


class InstructorApiTestCase(TrainingApiTestCase):
    def test_create_instructor_and_qualification(self) -> None:
        program = ProgramFactory()
        created = self.client.post(
            f"{BASE}/instructors/",
            {
                "last_name": "Петров",
                "first_name": "Пётр",
                "organization": str(self.interaction.organization.pk),
                "academic_degree": "candidate",
                "programs": [str(program.pk)],
            },
            format="json",
        )
        qualification = self.client.post(
            f"{BASE}/instructor-qualifications/",
            {"instructor": created.data["id"], "kind": "initial", "program": str(program.pk), "completed_at": "2026-01-15"},
            format="json",
        )

        self.assertEqual(created.status_code, status.HTTP_201_CREATED, msg=created.data)
        self.assertEqual(qualification.status_code, status.HTTP_201_CREATED, msg=qualification.data)
        self.assertEqual(TrainingInstructor.objects.get().qualifications.count(), 1)

    def test_organization_required_exactly_once(self) -> None:
        response = self.client.post(
            f"{BASE}/instructors/", {"last_name": "Петров", "first_name": "Пётр"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
