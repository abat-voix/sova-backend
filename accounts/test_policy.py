from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from accounts.models import SystemRole, UserRole
from accounts.policy import ALL_ACTIONS, READ_SCOPES, ROLE_ACTIONS, Action, Scope, allowed_actions, can, read_scope
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory


def create_user(role: str | None = None, **kwargs):
    """Создаёт пользователя и при необходимости назначает ему роль СОВА."""
    user = UserFactory(**kwargs)
    if role is not None:
        UserRole.objects.create(user=user, role=role)
    return user


class PolicyTableTestCase(TestCase):
    """Согласованность таблиц политики."""

    def test_every_role_has_an_entry(self) -> None:
        """У каждой прикладной роли есть строка в таблице операций."""
        self.assertEqual(set(ROLE_ACTIONS), set(SystemRole.values))

    def test_role_that_reads_a_section_has_a_scope(self) -> None:
        """Роль, которой разрешено чтение раздела, имеет в нём область видимости, и наоборот."""
        for role, actions in ROLE_ACTIONS.items():
            with self.subTest(role=role):
                self.assertEqual(
                    Action.INTERACTIONS_READ in actions,
                    role in READ_SCOPES["interactions"],
                )

    def test_observer_only_reads_interactions(self) -> None:
        """Наблюдатель во взаимодействиях только читает."""
        self.assertEqual(
            ROLE_ACTIONS[SystemRole.OBSERVER],
            {
                Action.INTERACTIONS_READ,
                Action.CONTRACTS_READ,
                Action.LICENSES_READ,
                Action.PROCESSES_READ,
                Action.REPORTS_READ,
                Action.REPORTS_EXPORT,
                Action.CATALOG_READ,
                Action.TRAINING_READ,
            },
        )


class CanTestCase(TestCase):
    """`can` и `allowed_actions`: учётная запись, роль, superuser, запись."""

    def test_anonymous_and_inactive_users_get_nothing(self) -> None:
        """Анонимный и неактивный пользователь не получают ни одной операции."""
        inactive_admin = create_user(SystemRole.PLATFORM_ADMIN, is_active=False)
        inactive_superuser = create_user(is_superuser=True, is_active=False)

        for user in (AnonymousUser(), inactive_admin, inactive_superuser):
            with self.subTest(user=user):
                self.assertEqual(allowed_actions(user), frozenset())
                self.assertFalse(can(user, Action.INTERACTIONS_READ))

    def test_user_without_role_gets_nothing(self) -> None:
        """Пользователь без роли, в том числе staff, не получает операций."""
        for user in (create_user(), create_user(is_staff=True)):
            with self.subTest(user=user):
                self.assertEqual(allowed_actions(user), frozenset())
                self.assertIsNone(read_scope(user, "interactions"))

    def test_superuser_gets_every_action_regardless_of_role(self) -> None:
        """Superuser получает все операции и видит всё — с ролью и без."""
        for role in (None, SystemRole.OBSERVER, SystemRole.KAM):
            user = create_user(role, is_superuser=True)
            with self.subTest(role=role):
                self.assertEqual(allowed_actions(user), ALL_ACTIONS)
                self.assertEqual(read_scope(user, "interactions"), Scope.ALL)

    def test_unknown_action_is_denied_even_to_superuser(self) -> None:
        """Неизвестный код операции — отказ, даже superuser."""
        self.assertFalse(can(create_user(is_superuser=True), "interactions.unknown"))

    def test_resource_outside_visibility_is_denied(self) -> None:
        """С записью операция разрешена, только если запись видна пользователю."""
        kam = create_user(SystemRole.KAM)
        own = InteractionFactory()
        responsible_service.assign(interaction=own, manager=kam, assigned_by=None)
        foreign = InteractionFactory()
        responsible_service.assign(interaction=foreign, manager=create_user(SystemRole.KAM), assigned_by=None)

        self.assertTrue(can(kam, Action.INTERACTIONS_UPDATE, own))
        self.assertFalse(can(kam, Action.INTERACTIONS_UPDATE, foreign))

    def test_observer_reads_any_record_but_changes_none(self) -> None:
        """Наблюдатель читает чужую запись, но не меняет её."""
        observer = create_user(SystemRole.OBSERVER)
        foreign = InteractionFactory()
        responsible_service.assign(interaction=foreign, manager=create_user(SystemRole.KAM), assigned_by=None)

        self.assertTrue(can(observer, Action.INTERACTIONS_READ, foreign))
        self.assertFalse(can(observer, Action.INTERACTIONS_UPDATE, foreign))
