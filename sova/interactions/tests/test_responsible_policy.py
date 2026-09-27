from django.test import TestCase

from accounts.models import Supervision, SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.services.responsible_policy import assignable_managers, removable_managers


def create_user(role: str | None = None, **kwargs):
    """Создаёт пользователя и при необходимости назначает ему роль СОВА."""
    user = UserFactory(**kwargs)
    if role is not None:
        UserRole.objects.create(user=user, role=role)
    return user


class ResponsiblePolicyTestCase(TestCase):
    """Кого роль может назначить и снять с ответственных."""

    def setUp(self) -> None:
        """Администратор, два руководителя, КАМы: свой, свободный, чужой, неактивный."""
        self.admin = create_user(SystemRole.PLATFORM_ADMIN)
        self.head = create_user(SystemRole.HEAD)
        self.other_head = create_user(SystemRole.HEAD)
        self.mine = create_user(SystemRole.KAM)
        self.free = create_user(SystemRole.KAM)
        self.foreign = create_user(SystemRole.KAM)
        self.inactive = create_user(SystemRole.KAM, is_active=False)
        Supervision.objects.create(kam=self.mine, head=self.head)
        Supervision.objects.create(kam=self.foreign, head=self.other_head)

    @staticmethod
    def ids(queryset) -> set[int]:
        """Идентификаторы пользователей выборки."""
        return set(queryset.values_list("pk", flat=True))

    def test_admin_assigns_active_kams_and_heads(self) -> None:
        """Администратор назначает активных КАМов и руководителей, но не администраторов."""
        self.assertEqual(
            self.ids(assignable_managers(self.admin)),
            {self.head.pk, self.other_head.pk, self.mine.pk, self.free.pk, self.foreign.pk},
        )

    def test_head_assigns_self_team_and_free(self) -> None:
        """Руководитель назначает себя, свою команду и свободных КАМов."""
        self.assertEqual(self.ids(assignable_managers(self.head)), {self.head.pk, self.mine.pk, self.free.pk})

    def test_kam_assigns_only_self(self) -> None:
        """КАМ назначает только себя."""
        self.assertEqual(self.ids(assignable_managers(self.mine)), {self.mine.pk})

    def test_user_without_role_assigns_nobody(self) -> None:
        """Пользователь без роли никого не назначает и не снимает."""
        user = create_user()

        # Проверяем оба набора
        self.assertEqual(self.ids(assignable_managers(user)), set())
        self.assertEqual(self.ids(removable_managers(user)), set())

    def test_admin_removes_anyone(self) -> None:
        """Администратор снимает любого, включая неактивных."""
        # Проверяем неактивного и чужого КАМа
        self.assertIn(self.inactive.pk, self.ids(removable_managers(self.admin)))
        self.assertIn(self.foreign.pk, self.ids(removable_managers(self.admin)))

    def test_head_removes_self_team_and_inactive(self) -> None:
        """Руководитель снимает себя, свою команду и неактивных КАМов, но не свободных активных и не чужих."""
        self.assertEqual(
            self.ids(removable_managers(self.head)),
            {self.head.pk, self.mine.pk, self.inactive.pk},
        )

    def test_kam_removes_nobody(self) -> None:
        """КАМ никого не снимает, даже себя."""
        self.assertEqual(self.ids(removable_managers(self.mine)), set())

    def test_stale_supervision_gives_no_rights(self) -> None:
        """КАМ, сменивший роль в обход сервиса, не назначается и не снимается через связь."""
        UserRole.objects.filter(user=self.mine).update(role=SystemRole.HEAD)

        # Проверяем, что устаревшая связь прав не даёт
        self.assertNotIn(self.mine.pk, self.ids(assignable_managers(self.head)))
        self.assertNotIn(self.mine.pk, self.ids(removable_managers(self.head)))
