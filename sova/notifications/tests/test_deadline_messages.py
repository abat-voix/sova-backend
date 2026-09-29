import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, override_settings

from sova.notifications.enum import NotifyEvent, NotifyType
from sova.notifications.services.deadline_messages import deadline_message_service
from sova.processes.services.deadlines import DeadlineItem

NOW = datetime(2026, 10, 15, 9, 0, tzinfo=ZoneInfo("Europe/Moscow"))
INTERACTION_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
PROCESS_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def item(kind, event, deadline, **names) -> DeadlineItem:
    """Пункт с описанием по умолчанию."""
    values = {
        "counterparty": "МГУ",
        "workflow_name": "B2B-сопровождение",
        "stage_name": "Подписание договора",
        "action_name": "Согласование документов",
        **names,
    }
    return DeadlineItem(notify_type=kind, event=event, object_id=uuid.uuid4(), deadline=deadline, **values)


class RenderDigestTest(SimpleTestCase):
    """Сводка на получателя."""

    def test_digest_groups_overdue_by_kind_and_lists_reminders(self) -> None:
        """Сводка: тема со счётчиками, блоки процессов, этапов, действий и «Скоро срок»."""
        items = [
            item(NotifyType.ACTION_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=7)),
            item(NotifyType.STAGE_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=5)),
            item(NotifyType.WORKFLOW_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=23)),
            item(NotifyType.ACTION_DEADLINE, NotifyEvent.REMINDER, NOW + timedelta(days=2), counterparty="СПбГУ"),
        ]

        text = deadline_message_service.render_digest(items=items, now=NOW)

        # Проверяем текст целиком: порядок блоков и формат строк
        self.assertEqual(
            text,
            "СОВА: сроки — просрочено 3, скоро срок 1\n"
            "\n"
            "Просроченные процессы:\n"
            "- МГУ — B2B-сопровождение: срок 22.09.2026, просрочено на 23 дн.\n"
            "\n"
            "Просроченные этапы:\n"
            "- МГУ — Подписание договора: срок 10.10.2026, просрочено на 5 дн.\n"
            "\n"
            "Просроченные действия:\n"
            "- МГУ — Подписание договора — Согласование документов: срок 08.10.2026, просрочено на 7 дн.\n"
            "\n"
            "Скоро срок:\n"
            "- СПбГУ — Подписание договора — Согласование документов (действие): срок 17.10.2026, осталось 2 дн.",
        )

    def test_partial_day_rounds_up(self) -> None:
        """Просрочка на несколько часов показывается как 1 день, а не 0."""
        text = deadline_message_service.render_digest(
            items=[item(NotifyType.STAGE_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(hours=3))],
            now=NOW,
        )

        # Проверяем округление вверх
        self.assertIn("просрочено на 1 дн.", text)


    def test_digest_without_brand_starts_with_capital(self) -> None:
        """Для колокольчика тема без префикса «СОВА:» и с заглавной буквы."""
        text = deadline_message_service.render_digest(
            items=[item(NotifyType.STAGE_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=1))],
            now=NOW,
            is_branded=False,
        )

        # Проверяем первую строку
        self.assertEqual(text.splitlines()[0], "Сроки — просрочено 1, скоро срок 0")

    @override_settings(FRONTEND_URL="https://sova.example.ru")
    def test_digest_puts_link_under_each_item(self) -> None:
        """Под пунктом со взаимодействием — его полная ссылка; пункт без взаимодействия — без ссылки."""
        stage = replace(
            item(NotifyType.STAGE_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=5)),
            interaction_id=INTERACTION_ID,
            workflow_instance_id=PROCESS_ID,
        )
        reminder = replace(
            item(NotifyType.ACTION_DEADLINE, NotifyEvent.REMINDER, NOW + timedelta(days=2)),
            interaction_id=INTERACTION_ID,
            workflow_instance_id=PROCESS_ID,
        )
        without_interaction = item(NotifyType.ACTION_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=7))

        text = deadline_message_service.render_digest(items=[stage, reminder, without_interaction], now=NOW)

        # Проверяем текст целиком: ссылка строкой ниже пункта с отступом
        self.assertEqual(
            text,
            "СОВА: сроки — просрочено 2, скоро срок 1\n"
            "\n"
            "Просроченные этапы:\n"
            "- МГУ — Подписание договора: срок 10.10.2026, просрочено на 5 дн.\n"
            f"  https://sova.example.ru/interactions?interaction={INTERACTION_ID}&process={PROCESS_ID}"
            f"&stage={stage.object_id}\n"
            "\n"
            "Просроченные действия:\n"
            "- МГУ — Подписание договора — Согласование документов: срок 08.10.2026, просрочено на 7 дн.\n"
            "\n"
            "Скоро срок:\n"
            "- МГУ — Подписание договора — Согласование документов (действие): срок 17.10.2026, осталось 2 дн.\n"
            f"  https://sova.example.ru/interactions?interaction={INTERACTION_ID}&process={PROCESS_ID}"
            f"&action={reminder.object_id}",
        )

    @override_settings(FRONTEND_URL="")
    def test_digest_without_frontend_url_has_no_links(self) -> None:
        """Без FRONTEND_URL сводка без ссылок — относительный адрес наружу не попадает."""
        text = deadline_message_service.render_digest(
            items=[
                replace(
                    item(NotifyType.STAGE_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=1)),
                    interaction_id=INTERACTION_ID,
                ),
            ],
            now=NOW,
        )

        # Проверяем, что ссылок нет
        self.assertNotIn("/interactions", text)


class RenderSingleTest(SimpleTestCase):
    """Отдельное сообщение на пункт."""

    def test_single_overdue_and_reminder(self) -> None:
        """Тема называет событие и вид контроля, тело — одна строка."""
        overdue = deadline_message_service.render_single(
            item=item(NotifyType.STAGE_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=1)),
            now=NOW,
        )
        reminder = deadline_message_service.render_single(
            item=item(NotifyType.ACTION_DEADLINE, NotifyEvent.REMINDER, NOW + timedelta(days=1)),
            now=NOW,
        )

        # Проверяем просрочку
        self.assertEqual(
            overdue,
            "СОВА: просрочено — этап\n\nМГУ — Подписание договора: срок 14.10.2026, просрочено на 1 дн.",
        )
        # Проверяем предупреждение
        self.assertEqual(
            reminder,
            "СОВА: скоро срок — действие\n\n"
            "МГУ — Подписание договора — Согласование документов: срок 16.10.2026, осталось 1 дн.",
        )

    def test_single_without_brand_starts_with_capital(self) -> None:
        """Для колокольчика тема отдельного сообщения без префикса «СОВА:»."""
        text = deadline_message_service.render_single(
            item=item(NotifyType.STAGE_DEADLINE, NotifyEvent.OVERDUE, NOW - timedelta(days=1)),
            now=NOW,
            is_branded=False,
        )

        # Проверяем первую строку
        self.assertEqual(text.splitlines()[0], "Просрочено — этап")


class DeadlineLinkTest(SimpleTestCase):
    """Ссылка пункта на взаимодействие с открытым процессом, этапом или действием."""

    def link_item(self, kind: str) -> DeadlineItem:
        """Пункт с id взаимодействия и процесса."""
        return replace(
            item(kind, NotifyEvent.OVERDUE, NOW),
            interaction_id=INTERACTION_ID,
            workflow_instance_id=PROCESS_ID,
        )

    def test_action_link_opens_action(self) -> None:
        """Действие — взаимодействие, процесс и действие."""
        link_item = self.link_item(NotifyType.ACTION_DEADLINE)

        # Проверяем адрес
        self.assertEqual(
            deadline_message_service.link(link_item),
            f"/interactions?interaction={INTERACTION_ID}&process={PROCESS_ID}&action={link_item.object_id}",
        )

    def test_stage_link_opens_stage(self) -> None:
        """Этап — взаимодействие, процесс и этап."""
        link_item = self.link_item(NotifyType.STAGE_DEADLINE)

        # Проверяем адрес
        self.assertEqual(
            deadline_message_service.link(link_item),
            f"/interactions?interaction={INTERACTION_ID}&process={PROCESS_ID}&stage={link_item.object_id}",
        )

    def test_workflow_link_opens_process(self) -> None:
        """Процесс — взаимодействие и процесс, без этапа и действия."""
        link_item = self.link_item(NotifyType.WORKFLOW_DEADLINE)

        # Проверяем адрес
        self.assertEqual(
            deadline_message_service.link(link_item),
            f"/interactions?interaction={INTERACTION_ID}&process={PROCESS_ID}",
        )

    def test_item_without_interaction_has_no_link(self) -> None:
        """Пункт без id взаимодействия — без ссылки."""
        # Проверяем пустую ссылку
        self.assertEqual(deadline_message_service.link(item(NotifyType.ACTION_DEADLINE, NotifyEvent.OVERDUE, NOW)), "")
