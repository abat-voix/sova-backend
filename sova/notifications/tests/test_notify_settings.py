import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from sova.core.tests.factories import UserFactory
from sova.notifications.enum import (
    DEADLINE_NOTIFY_TYPES,
    NOTIFY_TYPE_GROUPS,
    DeliveryMode,
    HeadMode,
    NotificationChannel,
    NotificationKind,
    NotifyEvent,
    NotifyType,
)
from sova.notifications.models import DeadlineDelivery, NotifySettings


class NotifySettingsDefaultsTest(TestCase):
    """Строки NotifySettings, созданные data-миграцией."""

    def test_migration_creates_one_row_per_type(self) -> None:
        """Миграция создаёт по строке на каждый тип уведомления."""
        # Проверяем набор типов
        self.assertEqual(
            set(NotifySettings.objects.values_list("notify_type", flat=True)),
            set(NotifyType.values),
        )

    def test_head_is_notified_about_stage_and_workflow_but_not_action(self) -> None:
        """По умолчанию руководитель узнаёт о просрочке этапа и процесса, но не действия."""
        rules = NotifySettings.objects.in_bulk(field_name="notify_type")

        # Проверяем флаг руководителя по типам сроков
        self.assertFalse(rules[NotifyType.ACTION_DEADLINE].is_notify_head)
        self.assertTrue(rules[NotifyType.STAGE_DEADLINE].is_notify_head)
        self.assertTrue(rules[NotifyType.WORKFLOW_DEADLINE].is_notify_head)

    def test_kam_assigned_goes_to_responsible_only(self) -> None:
        """Назначение КАМа по умолчанию — только ответственному, по всем каналам."""
        rule = NotifySettings.objects.get(notify_type=NotifyType.KAM_ASSIGNED)

        # Проверяем получателей
        self.assertTrue(rule.is_notify_responsible)
        self.assertFalse(rule.is_notify_head)
        # Проверяем каналы
        self.assertEqual(rule.channels(), list(NotificationChannel))

    def test_other_defaults(self) -> None:
        """Остальные значения по умолчанию совпадают со спекой."""
        rule = NotifySettings.objects.get(notify_type=NotifyType.ACTION_DEADLINE)

        # Проверяем включённость и получателей
        self.assertTrue(rule.is_enabled)
        self.assertTrue(rule.is_notify_responsible)
        self.assertTrue(rule.is_fallback_to_head)
        self.assertEqual(rule.head_mode, HeadMode.ASSIGNED_BY)
        # Проверяем, что предупреждения выключены, а их получатель по умолчанию — ответственный
        self.assertIsNone(rule.remind_before_days)
        self.assertTrue(rule.is_remind_responsible)
        self.assertFalse(rule.is_remind_head)
        # Проверяем доставку
        self.assertEqual(rule.delivery_mode, DeliveryMode.DIGEST)
        self.assertIsNone(rule.repeat_every_days)
        self.assertFalse(rule.is_skip_weekends)


class NotifyTypeGroupsTest(TestCase):
    """Соответствие типа уведомления группе колокольчика."""

    def test_every_type_has_group(self) -> None:
        """У каждого типа есть группа: новый тип без группы сломал бы отправку."""
        # Проверяем, что ключи словаря — ровно все типы
        self.assertEqual(set(NOTIFY_TYPE_GROUPS), set(NotifyType.values))

    def test_groups_of_types(self) -> None:
        """Типы сроков — «Сроки», назначение КАМа — «Назначения»."""
        # Проверяем типы сроков
        for notify_type in DEADLINE_NOTIFY_TYPES:
            self.assertEqual(NOTIFY_TYPE_GROUPS[notify_type], NotificationKind.DEADLINE)
        # Проверяем назначение КАМа
        self.assertEqual(NOTIFY_TYPE_GROUPS[NotifyType.KAM_ASSIGNED], NotificationKind.ASSIGNMENT)


class NotifySettingsMethodsTest(TestCase):
    """Методы NotifySettings."""

    def test_channels_follow_flags(self) -> None:
        """channels() возвращает только включённые каналы в порядке email, telegram, max, system."""
        rule = NotifySettings(
            is_channel_email=True,
            is_channel_telegram=False,
            is_channel_max=True,
            is_channel_system=True,
        )

        # Проверяем список каналов
        self.assertEqual(
            rule.channels(),
            [NotificationChannel.EMAIL, NotificationChannel.MAX, NotificationChannel.SYSTEM],
        )

    def test_recipient_flags_depend_on_event(self) -> None:
        """recipient_flags() берёт флаги просрочки или предупреждения по событию."""
        rule = NotifySettings(
            is_notify_responsible=True,
            is_notify_head=False,
            is_remind_responsible=False,
            is_remind_head=True,
        )

        # Проверяем флаги для просрочки
        self.assertEqual(rule.recipient_flags(NotifyEvent.OVERDUE), (True, False))
        # Проверяем флаги для предупреждения
        self.assertEqual(rule.recipient_flags(NotifyEvent.REMINDER), (False, True))


class DeadlineDeliveryTest(TestCase):
    """Журнал доставленных уведомлений о сроках."""

    def test_pair_item_recipient_is_unique(self) -> None:
        """Вторая запись о том же пункте, сроке и получателе нарушает уникальность."""
        recipient = UserFactory()
        values = {
            "notify_type": NotifyType.ACTION_DEADLINE,
            "event": NotifyEvent.OVERDUE,
            "object_id": uuid.uuid4(),
            "deadline": timezone.now(),
            "recipient": recipient,
            "last_sent_at": timezone.now(),
        }
        DeadlineDelivery.objects.create(**values)

        # Проверяем, что дубль отклоняется базой
        with self.assertRaises(IntegrityError):
            DeadlineDelivery.objects.create(**values)

    def test_journal_accepts_only_deadline_types(self) -> None:
        """В журнал сроков нельзя записать событийный тип."""
        choices = {value for value, _ in DeadlineDelivery._meta.get_field("notify_type").choices}

        # Проверяем набор допустимых типов
        self.assertEqual(choices, set(DEADLINE_NOTIFY_TYPES))


class NotifySettingsCleanTest(TestCase):
    """Валидация настроек типа уведомления."""

    def errors(self, notify_type: str, **values) -> set[str]:
        """Поля с ошибками full_clean() строки типа после изменения values; пусто — ошибок нет."""
        rule = NotifySettings.objects.get(notify_type=notify_type)
        for field, value in values.items():
            setattr(rule, field, value)
        try:
            rule.full_clean()
        except ValidationError as error:
            return set(error.message_dict)
        return set()

    def test_default_rows_are_valid(self) -> None:
        """Строки из data-миграции проходят валидацию — их можно сохранить в админке без правок."""
        for rule in NotifySettings.objects.all():
            # Проверяем, что строка по умолчанию валидна
            self.assertEqual(self.errors(rule.notify_type), set(), rule.notify_type)

    def test_event_type_rejects_deadline_schedule(self) -> None:
        """У событийного типа нельзя задать предупреждение и повтор."""
        errors = self.errors(NotifyType.KAM_ASSIGNED, remind_before_days=2, repeat_every_days=1)

        # Проверяем ошибки на обоих полях расписания
        self.assertEqual(errors, {"remind_before_days", "repeat_every_days"})

    def test_deadline_type_accepts_schedule(self) -> None:
        """У типа сроков предупреждение и повтор допустимы."""
        errors = self.errors(NotifyType.ACTION_DEADLINE, remind_before_days=2, repeat_every_days=1)

        # Проверяем отсутствие ошибок
        self.assertEqual(errors, set())

    def test_zero_days_are_rejected(self) -> None:
        """0 дней не принимается: пустое значение уже означает «выключено»."""
        errors = self.errors(NotifyType.ACTION_DEADLINE, remind_before_days=0, repeat_every_days=0)

        # Проверяем ошибки валидаторов
        self.assertEqual(errors, {"remind_before_days", "repeat_every_days"})

    def test_enabled_type_needs_channel(self) -> None:
        """Включённый тип без каналов не сохраняется."""
        no_channels = {
            "is_channel_email": False,
            "is_channel_telegram": False,
            "is_channel_max": False,
            "is_channel_system": False,
        }

        # Проверяем ошибку у включённого типа
        self.assertEqual(self.errors(NotifyType.KAM_ASSIGNED, **no_channels), {"is_channel_system"})
        # Проверяем, что выключенный тип без каналов допустим
        self.assertEqual(self.errors(NotifyType.KAM_ASSIGNED, is_enabled=False, **no_channels), set())

    def test_enabled_type_needs_recipient(self) -> None:
        """Включённый тип без получателей не сохраняется."""
        errors = self.errors(NotifyType.KAM_ASSIGNED, is_notify_responsible=False, is_notify_head=False)

        # Проверяем ошибку получателей
        self.assertEqual(errors, {"is_notify_responsible"})

    def test_reminder_needs_recipient(self) -> None:
        """Предупреждение о сроке без получателей предупреждения не сохраняется."""
        errors = self.errors(
            NotifyType.ACTION_DEADLINE,
            remind_before_days=2,
            is_remind_responsible=False,
            is_remind_head=False,
        )

        # Проверяем ошибку получателей предупреждения
        self.assertEqual(errors, {"is_remind_responsible"})
