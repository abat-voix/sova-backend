from django.test import TestCase

from accounts.models import Supervision, SystemRole, UserRole
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

    def recipients(self, rule, responsibles, event=NotifyEvent.OVERDUE, interaction=None) -> list:
        """Получатели для взаимодействия из setUp."""
        interaction = interaction or self.interaction
        resolver = DeadlineRecipientResolver(interaction_ids=[interaction.pk])
        return resolver.recipients(rule=rule, event=event, interaction_id=interaction.pk, responsibles=responsibles)

    def test_interaction_responsibles_are_active_kams(self) -> None:
        """interaction_responsibles() возвращает всех активных КАМов взаимодействия в порядке назначения."""
        second = make_user(SystemRole.KAM)
        ResponsibleFactory(interaction=self.interaction, manager=second, assigned_by=self.head)
        ResponsibleFactory(interaction=self.interaction, manager=make_user(SystemRole.KAM, is_active=False))
        resolver = DeadlineRecipientResolver(interaction_ids=[self.interaction.pk])

        # Проверяем, что найдены оба активных КАМа, деактивированный пропущен
        self.assertEqual(resolver.interaction_responsibles(self.interaction.pk), [self.kam, second])

    def test_interaction_responsibles_are_empty_without_current_record(self) -> None:
        """Без действующего назначения ответственных нет."""
        interaction = InteractionFactory()
        resolver = DeadlineRecipientResolver(interaction_ids=[interaction.pk])

        # Проверяем отсутствие ответственных
        self.assertEqual(resolver.interaction_responsibles(interaction.pk), [])

    def test_all_responsibles_are_notified(self) -> None:
        """Несколько ответственных — письмо каждому."""
        second = make_user(SystemRole.KAM)

        # Проверяем состав получателей
        self.assertEqual(self.recipients(self.rule(), responsibles=[self.kam, second]), [self.kam, second])

    def test_every_assigning_head_is_notified(self) -> None:
        """head_mode=assigned_by и КАМы назначены разными руководителями — письмо каждому из них."""
        ResponsibleFactory(interaction=self.interaction, manager=make_user(SystemRole.KAM), assigned_by=self.other_head)
        rule = self.rule(is_notify_responsible=False, is_notify_head=True)

        # Проверяем, что получили оба назначивших руководителя
        self.assertEqual(self.recipients(rule, responsibles=[]), [self.head, self.other_head])

    def test_only_responsible(self) -> None:
        """Флаг только ответственного — письмо только КАМу."""
        # Проверяем состав получателей
        self.assertEqual(self.recipients(self.rule(), responsibles=[self.kam]), [self.kam])

    def test_responsible_and_assigning_head(self) -> None:
        """Оба флага и head_mode=assigned_by — КАМ и назначивший его руководитель."""
        rule = self.rule(is_notify_head=True)

        # Проверяем состав и порядок получателей
        self.assertEqual(self.recipients(rule, responsibles=[self.kam]), [self.kam, self.head])

    def test_all_heads_mode(self) -> None:
        """head_mode=all_heads — все активные руководители."""
        rule = self.rule(is_notify_responsible=False, is_notify_head=True, head_mode=HeadMode.ALL_HEADS)

        # Проверяем, что получили оба руководителя
        self.assertEqual(set(self.recipients(rule, responsibles=[self.kam])), {self.head, self.other_head})

    def test_fallback_to_head_without_responsible(self) -> None:
        """Нет ответственного и включён запасной вариант — письмо руководителю."""
        # Проверяем, что письмо уходит назначившему руководителю
        self.assertEqual(self.recipients(self.rule(), responsibles=[]), [self.head])

    def test_no_fallback_means_nobody(self) -> None:
        """Нет ответственного и запасной вариант выключен — получателей нет."""
        rule = self.rule(is_fallback_to_head=False)

        # Проверяем пустой список
        self.assertEqual(self.recipients(rule, responsibles=[]), [])

    def test_inactive_responsible_triggers_fallback(self) -> None:
        """Деактивированный КАМ считается отсутствующим ответственным."""
        inactive = make_user(SystemRole.KAM, is_active=False)

        # Проверяем, что письмо ушло руководителю, а не неактивному КАМу
        self.assertEqual(self.recipients(self.rule(), responsibles=[inactive]), [self.head])

    def test_head_is_not_duplicated(self) -> None:
        """Руководитель через запасной вариант и через флаг руководителя получает одно письмо."""
        rule = self.rule(is_notify_head=True)

        # Проверяем, что руководитель в списке один раз
        self.assertEqual(self.recipients(rule, responsibles=[]), [self.head])

    def test_responsible_who_is_head_is_not_duplicated(self) -> None:
        """Ответственный, который сам назначил себя руководителем, получает одно письмо."""
        interaction = InteractionFactory()
        ResponsibleFactory(interaction=interaction, manager=self.head, assigned_by=self.head)
        rule = self.rule(is_notify_head=True)

        # Проверяем, что получатель один
        self.assertEqual(self.recipients(rule, responsibles=[self.head], interaction=interaction), [self.head])

    def test_assigned_by_not_head_falls_back_to_all_heads(self) -> None:
        """assigned_by без роли head (администратор платформы) — все руководители."""
        interaction = InteractionFactory()
        admin = make_user(SystemRole.PLATFORM_ADMIN)
        ResponsibleFactory(interaction=interaction, manager=self.kam, assigned_by=admin)
        rule = self.rule(is_notify_responsible=False, is_notify_head=True)

        # Проверяем, что администратор не получает, а оба руководителя получают
        self.assertEqual(
            set(self.recipients(rule, responsibles=[self.kam], interaction=interaction)),
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
        self.assertEqual(set(self.recipients(rule, [], interaction=empty)), {self.head, self.other_head})
        # Проверяем неактивный assigned_by — сам он в списке не появляется
        self.assertEqual(set(self.recipients(rule, [], interaction=inactive)), {self.head, self.other_head})

    def test_reminder_uses_reminder_flags(self) -> None:
        """Для предупреждения берутся флаги is_remind_*."""
        rule = self.rule(is_remind_responsible=False, is_remind_head=True)

        # Проверяем, что предупреждение уходит только руководителю
        self.assertEqual(self.recipients(rule, responsibles=[self.kam], event=NotifyEvent.REMINDER), [self.head])


class SupervisorHeadModeTest(TestCase):
    """head_mode=supervisor — руководители действующих КАМов взаимодействия."""

    def setUp(self) -> None:
        """Взаимодействие с двумя КАМами разных руководителей и руководитель без команды."""
        self.head = make_user(SystemRole.HEAD)
        self.second_head = make_user(SystemRole.HEAD)
        self.free_head = make_user(SystemRole.HEAD)
        self.kam = make_user(SystemRole.KAM)
        self.second_kam = make_user(SystemRole.KAM)
        Supervision.objects.create(kam=self.kam, head=self.head)
        Supervision.objects.create(kam=self.second_kam, head=self.second_head)
        self.interaction = InteractionFactory()
        ResponsibleFactory(interaction=self.interaction, manager=self.kam, assigned_by=self.free_head)
        self.rule = NotifySettings(
            is_notify_responsible=False,
            is_notify_head=True,
            is_fallback_to_head=True,
            head_mode=HeadMode.SUPERVISOR,
        )

    def heads(self, interaction=None) -> list:
        """Руководители-получатели для взаимодействия."""
        interaction = interaction or self.interaction
        resolver = DeadlineRecipientResolver(interaction_ids=[interaction.pk])
        return resolver.recipients(
            rule=self.rule,
            event=NotifyEvent.OVERDUE,
            interaction_id=interaction.pk,
            responsibles=[],
        )

    def test_supervisor_of_kam(self) -> None:
        """Уведомляется руководитель КАМа, а не назначивший его."""
        self.assertEqual(self.heads(), [self.head])

    def test_supervisors_of_every_kam(self) -> None:
        """КАМы с разными руководителями — уведомляются оба руководителя."""
        ResponsibleFactory(interaction=self.interaction, manager=self.second_kam)

        self.assertEqual(sorted(self.heads(), key=lambda user: user.pk), [self.head, self.second_head])

    def test_kam_without_supervisor_falls_back_to_all_heads(self) -> None:
        """У КАМа нет руководителя — все активные руководители."""
        Supervision.objects.filter(kam=self.kam).delete()

        self.assertEqual(self.heads(), [self.head, self.second_head, self.free_head])

    def test_inactive_supervisor_falls_back_to_all_heads(self) -> None:
        """Руководитель КАМа неактивен — все активные руководители."""
        self.head.is_active = False
        self.head.save()

        self.assertEqual(self.heads(), [self.second_head, self.free_head])

    def test_supervisor_without_head_role_is_ignored(self) -> None:
        """Связь устарела (руководитель сменил роль в обход сервиса) — все активные руководители."""
        UserRole.objects.filter(user=self.head).update(role=SystemRole.KAM)

        self.assertEqual(self.heads(), [self.second_head, self.free_head])

    def test_interaction_without_kams_falls_back_to_all_heads(self) -> None:
        """У взаимодействия нет КАМов — все активные руководители."""
        self.assertEqual(self.heads(interaction=InteractionFactory()), [self.head, self.second_head, self.free_head])
