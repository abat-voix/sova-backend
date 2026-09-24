from unittest.mock import patch

from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory
from sova.notifications.enum import NotificationChannel
from sova.processes.tests.factories import ActionInstanceFactory


@patch("sova.notifications.services.event_notification.send_event_notification")
class ResponsibleNotificationTest(TestCase):
    """Уведомление нового КАМа при назначении ответственным."""

    def setUp(self) -> None:
        """Взаимодействие с вузом, КАМ и руководитель."""
        self.interaction = InteractionFactory()
        self.kam = UserFactory()
        self.head = UserFactory()

    def assign(self, manager, assigned_by) -> None:
        """Назначение с выполнением on_commit."""
        with self.captureOnCommitCallbacks(execute=True):
            responsible_service.assign(interaction=self.interaction, manager=manager, assigned_by=assigned_by)

    def system_texts(self, task) -> list[str]:
        """Тексты постановок в колокольчик."""
        return [
            item.kwargs["text"]
            for item in task.delay.call_args_list
            if item.kwargs["channels"] == [NotificationChannel.SYSTEM]
        ]

    def test_new_kam_is_notified(self, task) -> None:
        """Новый КАМ получает уведомление со ссылкой на взаимодействие."""
        self.assign(manager=self.kam, assigned_by=self.head)

        # Проверяем текст без строки о задачах
        self.assertEqual(self.system_texts(task), [f"Вас назначили КАМом — {self.interaction.university.name}"])
        # Проверяем получателя и ссылку
        kwargs = task.delay.call_args_list[0].kwargs
        self.assertEqual(kwargs["user_ids"], [self.kam.pk])
        self.assertEqual(kwargs["link"], f"/interactions?interaction={self.interaction.pk}")

    def test_open_tasks_are_not_transferred(self, task) -> None:
        """Открытые задачи взаимодействия новому КАМу не передаются — в тексте нет строки о задачах."""
        instance = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=self.interaction,
            responsible=None,
        )

        self.assign(manager=self.kam, assigned_by=self.head)
        instance.refresh_from_db()

        # Проверяем, что задача осталась в пуле
        self.assertIsNone(instance.responsible_id)
        # Проверяем текст без строки о задачах
        self.assertEqual(self.system_texts(task), [f"Вас назначили КАМом — {self.interaction.university.name}"])

    def test_second_kam_is_notified(self, task) -> None:
        """Второй КАМ взаимодействия тоже получает уведомление о назначении."""
        self.assign(manager=self.kam, assigned_by=self.head)
        task.delay.reset_mock()
        second = UserFactory()

        self.assign(manager=second, assigned_by=self.head)

        # Проверяем получателя
        self.assertEqual(task.delay.call_args_list[0].kwargs["user_ids"], [second.pk])

    def test_same_kam_again_sends_nothing(self, task) -> None:
        """Повторное назначение того же КАМа ничего не отправляет."""
        self.assign(manager=self.kam, assigned_by=self.head)
        task.delay.reset_mock()

        self.assign(manager=self.kam, assigned_by=self.head)

        # Проверяем отсутствие новых постановок
        task.delay.assert_not_called()

    def test_self_assignment_sends_nothing(self, task) -> None:
        """Руководитель назначил КАМом самого себя — уведомления нет."""
        self.assign(manager=self.head, assigned_by=self.head)

        # Проверяем отсутствие постановок
        task.delay.assert_not_called()
