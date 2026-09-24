from django.test import TestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import InteractionFactory, ResponsibleFactory
from sova.notifications.enum import HeadMode, NotifyEvent
from sova.notifications.models import NotifySettings
from sova.processes.services.deadline_recipients import DeadlineRecipientResolver


def make_user(role: str | None = None, **kwargs):
    """Пользователь с прикладной ролью."""
    user = UserFactory(**kwargs)
    if role is not None:
        UserRole.objects.create(user=user, role=role)
    return user


class DeadlineRecipientResolverTest(TestCase):
    """Тесты выбора получателей уведомления о сроке."""

    def setUp(self) -> None:
        """Взаимодействие с КАМом, назначенным руководителем, и ещё один руководитель."""
        self.head = make_user(SystemRole.HEAD)
        self.other_head = make_user(SystemRole.HEAD)
        self.kam = make_user(SystemRole.KAM)
        self.interaction = InteractionFactory()
        ResponsibleFactory(interaction=self.interaction, manager=self.kam, assigned_by=self.head)

    def rule(self, **flags) -> NotifySettings:
        """Правило в памяти: по умолчанию только ответственному, запасной вариант включён."""
        values = {
            "is_notify_responsible": True,
            "is_notify_head": False,
            "is_fallback_to_head": True,
            "head_mode": HeadMode.ASSIGNED_BY,
            **flags,
        }
        return NotifySettings(**values)

    def recipients(self, rule, responsible, event=NotifyEvent.OVERDUE, interaction=None) -> list:
        """Получатели для взаимодействия из setUp."""
        interaction = interaction or self.interaction
        resolver = DeadlineRecipientResolver(interaction_ids=[interaction.pk])
        return resolver.recipients(rule=rule, event=event, interaction_id=interaction.pk, responsible=responsible)

    def test_interaction_responsible_is_active_kam(self) -> None:
        """interaction_responsible() возвращает активного КАМа взаимодействия."""
        resolver = DeadlineRecipientResolver(interaction_ids=[self.interaction.pk])

        # Проверяем, что найден КАМ
        self.assertEqual(resolver.interaction_responsible(self.interaction.pk), self.kam)

    def test_interaction_responsible_is_none_without_current_record(self) -> None:
        """Без действующего назначения ответственного нет."""
        interaction = InteractionFactory()
        resolver = DeadlineRecipientResolver(interaction_ids=[interaction.pk])

        # Проверяем отсутствие ответственного
        self.assertIsNone(resolver.interaction_responsible(interaction.pk))

    def test_only_responsible(self) -> None:
        """Флаг только ответственного — письмо только КАМу."""
        # Проверяем состав получателей
        self.assertEqual(self.recipients(self.rule(), responsible=self.kam), [self.kam])

    def test_responsible_and_assigning_head(self) -> None:
        """Оба флага и head_mode=assigned_by — КАМ и назначивший его руководитель."""
        rule = self.rule(is_notify_head=True)

        # Проверяем состав и порядок получателей
        self.assertEqual(self.recipients(rule, responsible=self.kam), [self.kam, self.head])

    def test_all_heads_mode(self) -> None:
        """head_mode=all_heads — все активные руководители."""
        rule = self.rule(is_notify_responsible=False, is_notify_head=True, head_mode=HeadMode.ALL_HEADS)

        # Проверяем, что получили оба руководителя
        self.assertEqual(set(self.recipients(rule, responsible=self.kam)), {self.head, self.other_head})

    def test_fallback_to_head_without_responsible(self) -> None:
        """Нет ответственного и включён запасной вариант — письмо руководителю."""
        # Проверяем, что письмо уходит назначившему руководителю
        self.assertEqual(self.recipients(self.rule(), responsible=None), [self.head])

    def test_no_fallback_means_nobody(self) -> None:
        """Нет ответственного и запасной вариант выключен — получателей нет."""
        rule = self.rule(is_fallback_to_head=False)

        # Проверяем пустой список
        self.assertEqual(self.recipients(rule, responsible=None), [])

    def test_inactive_responsible_triggers_fallback(self) -> None:
        """Деактивированный КАМ считается отсутствующим ответственным."""
        inactive = make_user(SystemRole.KAM, is_active=False)

        # Проверяем, что письмо ушло руководителю, а не неактивному КАМу
        self.assertEqual(self.recipients(self.rule(), responsible=inactive), [self.head])

    def test_head_is_not_duplicated(self) -> None:
        """Руководитель через запасной вариант и через флаг руководителя получает одно письмо."""
        rule = self.rule(is_notify_head=True)

        # Проверяем, что руководитель в списке один раз
        self.assertEqual(self.recipients(rule, responsible=None), [self.head])

    def test_responsible_who_is_head_is_not_duplicated(self) -> None:
        """Ответственный, который сам назначил себя руководителем, получает одно письмо."""
        interaction = InteractionFactory()
        ResponsibleFactory(interaction=interaction, manager=self.head, assigned_by=self.head)
        rule = self.rule(is_notify_head=True)

        # Проверяем, что получатель один
        self.assertEqual(self.recipients(rule, responsible=self.head, interaction=interaction), [self.head])

    def test_assigned_by_not_head_falls_back_to_all_heads(self) -> None:
        """assigned_by без роли head (администратор платформы) — все руководители."""
        interaction = InteractionFactory()
        admin = make_user(SystemRole.PLATFORM_ADMIN)
        ResponsibleFactory(interaction=interaction, manager=self.kam, assigned_by=admin)
        rule = self.rule(is_notify_responsible=False, is_notify_head=True)

        # Проверяем, что администратор не получает, а оба руководителя получают
        self.assertEqual(
            set(self.recipients(rule, responsible=self.kam, interaction=interaction)),
            {self.head, self.other_head},
        )

    def test_empty_or_inactive_assigned_by_falls_back_to_all_heads(self) -> None:
        """Пустой или деактивированный assigned_by — все активные руководители."""
        inactive_head = make_user(SystemRole.HEAD, is_active=False)
        empty = InteractionFactory()
        ResponsibleFactory(interaction=empty, manager=self.kam, assigned_by=None)
        inactive = InteractionFactory()
        ResponsibleFactory(interaction=inactive, manager=self.kam, assigned_by=inactive_head)
        rule = self.rule(is_notify_responsible=False, is_notify_head=True)

        # Проверяем пустой assigned_by
        self.assertEqual(set(self.recipients(rule, None, interaction=empty)), {self.head, self.other_head})
        # Проверяем неактивный assigned_by — сам он в списке не появляется
        self.assertEqual(set(self.recipients(rule, None, interaction=inactive)), {self.head, self.other_head})

    def test_reminder_uses_reminder_flags(self) -> None:
        """Для предупреждения берутся флаги is_remind_*."""
        rule = self.rule(is_remind_responsible=False, is_remind_head=True)

        # Проверяем, что предупреждение уходит только руководителю
        self.assertEqual(self.recipients(rule, responsible=self.kam, event=NotifyEvent.REMINDER), [self.head])
