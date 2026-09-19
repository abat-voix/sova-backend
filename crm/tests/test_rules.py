from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from crm.rules import is_assigned_manager
from crm.tests.factories import (
    B2CClientFactory,
    InteractionFactory,
    ResponsibleAssignmentFactory,
    UniversityFactory,
    UserFactory,
    WorkflowInstanceFactory,
)


class IsAssignedManagerTestCase(TestCase):
    """Тесты предиката crm.rules.is_assigned_manager."""

    def setUp(self) -> None:
        """Подготовка данных перед каждым тестом."""
        self.manager = UserFactory()
        self.university = UniversityFactory()
        ResponsibleAssignmentFactory(university=self.university, manager=self.manager)
        self.interaction = InteractionFactory(university=self.university)
        self.instance = WorkflowInstanceFactory(interaction=self.interaction)

    def test_true_for_assigned_manager(self) -> None:
        """КАМ, назначенный ответственным за вуз сделки, проходит проверку."""
        self.assertTrue(is_assigned_manager(self.manager, self.instance))

    def test_false_for_other_user(self) -> None:
        """Посторонний пользователь не проходит проверку."""
        self.assertFalse(is_assigned_manager(UserFactory(), self.instance))

    def test_false_when_no_responsible_assigned(self) -> None:
        """Вуз без назначенного ответственного — проверка не проходит ни для кого."""
        interaction = InteractionFactory()
        instance = WorkflowInstanceFactory(interaction=interaction)

        self.assertFalse(is_assigned_manager(self.manager, instance))

    def test_false_for_b2c_interaction_without_responsible(self) -> None:
        """У B2C-сделки без назначенного ответственного — предикат не падает, просто False."""
        interaction = InteractionFactory(university=None, b2c_client=B2CClientFactory())
        instance = WorkflowInstanceFactory(interaction=interaction)

        self.assertFalse(is_assigned_manager(self.manager, instance))

    def test_true_for_assigned_manager_of_b2c_client(self) -> None:
        """
        Регрессионный тест на баг: раньше is_assigned_manager проверял только

        university_id, и для ЛЮБОЙ B2C-сделки всегда возвращал False — назначить
        КАМа на B2C-клиента было физически некуда (UniversityResponsible не умел
        ссылаться на B2CClient). Теперь ResponsibleAssignment поддерживает оба
        контрагента, и КАМ, назначенный на B2C-клиента, должен проходить проверку.
        """
        b2c_manager = UserFactory()
        b2c_client = B2CClientFactory()
        ResponsibleAssignmentFactory(university=None, b2c_client=b2c_client, manager=b2c_manager)
        interaction = InteractionFactory(university=None, b2c_client=b2c_client)
        instance = WorkflowInstanceFactory(interaction=interaction)

        self.assertTrue(is_assigned_manager(b2c_manager, instance))


class WorkflowTransitionPermTestCase(TestCase):
    """Тесты композитного правила workflow.transition (Group/Permission + object-level predicate)."""

    def setUp(self) -> None:
        """Подготовка данных перед каждым тестом."""
        self.manager = UserFactory()
        self.university = UniversityFactory()
        ResponsibleAssignmentFactory(university=self.university, manager=self.manager)
        self.instance = WorkflowInstanceFactory(interaction=InteractionFactory(university=self.university))

    def test_assigned_manager_passes_without_explicit_permission(self) -> None:
        """Ответственный КАМ проходит правило даже без явного Permission can_transition_backward."""
        self.assertTrue(self.manager.has_perm("workflow.transition", self.instance))

    def test_user_with_permission_passes_regardless_of_assignment(self) -> None:
        """Пользователь с правом can_transition_backward проходит правило, даже не будучи КАМом вуза."""
        group = Group.objects.create(name="Руководитель-тест")
        group.permissions.add(Permission.objects.get(codename="can_transition_backward"))
        other_user = UserFactory()
        other_user.groups.add(group)

        self.assertTrue(other_user.has_perm("workflow.transition", self.instance))

    def test_unrelated_user_without_permission_fails(self) -> None:
        """Посторонний пользователь без права и без назначения — правило не проходит."""
        self.assertFalse(UserFactory().has_perm("workflow.transition", self.instance))
