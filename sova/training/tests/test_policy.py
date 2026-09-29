from django.test import TestCase

from accounts.models import SystemRole, UserRole
from accounts.policy import Action, can, visible_queryset
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory, InteractionProgramFactory
from sova.training.tests.factories import TrainingStreamFactory


def create_user(role: str):
    user = UserFactory()
    UserRole.objects.create(user=user, role=role)
    return user


class TrainingPolicyTestCase(TestCase):
    """Раздел `training` политики: потоки видны вместе со взаимодействием программы."""

    def setUp(self) -> None:
        self.kam = create_user(SystemRole.KAM)
        own = InteractionFactory()
        responsible_service.assign(interaction=own, manager=self.kam, assigned_by=None)
        self.own = TrainingStreamFactory(interaction_program=InteractionProgramFactory(interaction=own))
        foreign = InteractionFactory()
        responsible_service.assign(interaction=foreign, manager=create_user(SystemRole.KAM), assigned_by=None)
        self.foreign = TrainingStreamFactory(interaction_program=InteractionProgramFactory(interaction=foreign))

    def test_kam_sees_streams_of_own_interactions(self) -> None:
        self.assertEqual(list(visible_queryset(self.kam, "training")), [self.own])

    def test_observer_and_admin_see_all(self) -> None:
        for role in (SystemRole.OBSERVER, SystemRole.PLATFORM_ADMIN):
            self.assertEqual(set(visible_queryset(create_user(role), "training")), {self.own, self.foreign}, role)

    def test_user_without_role_sees_nothing(self) -> None:
        self.assertFalse(visible_queryset(UserFactory(), "training").exists())

    def test_actions_by_role(self) -> None:
        observer = create_user(SystemRole.OBSERVER)
        self.assertTrue(can(observer, Action.TRAINING_READ))
        self.assertFalse(can(observer, Action.TRAINING_UPDATE))
        for role in (SystemRole.KAM, SystemRole.HEAD, SystemRole.PLATFORM_ADMIN):
            user = create_user(role)
            self.assertTrue(can(user, Action.TRAINING_READ) and can(user, Action.TRAINING_UPDATE), role)

    def test_update_checks_record_visibility(self) -> None:
        self.assertTrue(can(self.kam, Action.TRAINING_UPDATE, self.own))
        self.assertFalse(can(self.kam, Action.TRAINING_UPDATE, self.foreign))
