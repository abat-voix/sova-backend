from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from accounts.models import SystemRole, UserRole
from accounts.policy import Action, can
from sova.core.tests.factories import UserFactory
from sova.training.models import LearnerPersonalDataAccessLog
from sova.training.tests.factories import (
    LearnerFactory,
    LearnerPersonalDataFactory,
    TrainingInstructorFactory,
    TrainingStreamFactory,
)


def create_user(role: str | None = None, **kwargs):
    user = UserFactory(**kwargs)
    if role is not None:
        UserRole.objects.create(user=user, role=role)
    return user


def login(client, user) -> None:
    """Вход с действующим OIDC id token: иначе GET админки уходит на продление сессии в Keycloak."""
    client.force_login(user)
    session = client.session
    session["oidc_id_token_expiration"] = 2**31
    session.save()


class PersonalDataPolicyTestCase(TestCase):
    def test_only_platform_admin_reads_personal_data(self) -> None:
        self.assertTrue(can(create_user(SystemRole.PLATFORM_ADMIN), Action.TRAINING_PERSONAL_DATA_READ))
        for role in (SystemRole.KAM, SystemRole.HEAD, SystemRole.OBSERVER):
            self.assertFalse(can(create_user(role), Action.TRAINING_PERSONAL_DATA_READ), role)


class LearnerAdminTestCase(TestCase):
    def setUp(self) -> None:
        self.learner = LearnerFactory(email="cherepanona.s@test.ru", phone="79990234365")
        self.data = LearnerPersonalDataFactory(learner=self.learner, snils="123-456-789 45")

    def test_list_shows_masks(self) -> None:
        login(self.client, create_user(is_superuser=True, is_staff=True))

        response = self.client.get(reverse("admin:training_learner_changelist"))

        self.assertContains(response, "c***@test.ru")
        self.assertNotContains(response, "cherepanona.s@test.ru")

    def test_personal_data_view_is_logged(self) -> None:
        admin = create_user(is_superuser=True, is_staff=True)
        login(self.client, admin)

        response = self.client.get(reverse("admin:training_learnerpersonaldata_change", args=(self.data.pk,)))

        self.assertContains(response, "123-456-789 45")
        log = LearnerPersonalDataAccessLog.objects.get()
        self.assertEqual((log.user, log.learner), (admin, self.learner))

    def test_staff_without_admin_role_cannot_open_personal_data(self) -> None:
        login(self.client, create_user(SystemRole.HEAD, is_staff=True))

        response = self.client.get(reverse("admin:training_learnerpersonaldata_change", args=(self.data.pk,)))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(LearnerPersonalDataAccessLog.objects.exists())


class NoManualAddingAdminTestCase(TestCase):
    """Обучающиеся приходят только из файла «Пользователи»: в админке их не добавляют."""

    def test_add_views_are_forbidden(self) -> None:
        login(self.client, create_user(is_superuser=True, is_staff=True))

        for model in ("learner", "learnerpersonaldata"):
            response = self.client.get(reverse(f"admin:training_{model}_add"))
            self.assertEqual(response.status_code, 403, model)



class PaymentAdminRemovedTestCase(TestCase):
    def test_no_payment_admin(self) -> None:
        """Оплата — только признак участника заявки, отдельной админки оплат нет."""
        with self.assertRaises(NoReverseMatch):
            reverse("admin:training_trainingpayment_changelist")


class TrainingStreamAdminTestCase(TestCase):
    def test_instructors_are_read_only(self) -> None:
        """Назначения видны в карточке потока, но меняют их только через API — с проверками сервиса."""
        stream = TrainingStreamFactory()
        instructor = TrainingInstructorFactory(organization=stream.interaction_program.interaction.organization)
        stream.instructors.add(instructor)
        login(self.client, create_user(is_superuser=True, is_staff=True))

        response = self.client.get(reverse("admin:training_trainingstream_change", args=(stream.pk,)))

        self.assertContains(response, instructor.full_name)
        formset = response.context["inline_admin_formsets"][0]
        self.assertFalse(formset.has_add_permission)
        self.assertFalse(formset.formset.can_delete)
