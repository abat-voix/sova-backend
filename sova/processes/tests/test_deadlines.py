from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Responsible
from sova.interactions.tests.factories import InteractionFactory, ResponsibleFactory
from sova.notifications.enum import NotifyEvent, NotifyType
from sova.notifications.models import NotifySettings
from sova.processes.enum import ActionInstanceStatus, StageInstanceStatus, WorkflowInstanceStatus
from sova.processes.models import WorkflowInstance
from sova.processes.services.deadlines import DeadlineService
from sova.processes.tests.factories import ActionInstanceFactory, StageInstanceFactory, WorkflowInstanceFactory


class DeadlineServiceTestCase(TestCase):
    """Общие помощники: взаимодействие с КАМом и руководителем, фиксированное «сейчас»."""

    def setUp(self) -> None:
        """КАМ назначен руководителем на взаимодействие."""
        self.now = timezone.now()
        self.head = UserFactory()
        UserRole.objects.create(user=self.head, role=SystemRole.HEAD)
        self.kam = UserFactory()
        self.interaction = InteractionFactory()
        ResponsibleFactory(interaction=self.interaction, manager=self.kam, assigned_by=self.head)
        self.process = WorkflowInstanceFactory(interaction=self.interaction)
        self.stage = StageInstanceFactory(workflow_instance=self.process)

    def action(self, planned_end=None, duration=5, **kwargs):
        """Действие этапа из setUp; по умолчанию просрочено на сутки."""
        return ActionInstanceFactory(
            stage_instance=kwargs.pop("stage_instance", self.stage),
            action__default_duration_days=duration,
            planned_end=planned_end if planned_end is not None else self.now - timedelta(days=1),
            responsible=kwargs.pop("responsible", self.kam),
            **kwargs,
        )

    def items(self, kind: str) -> list:
        """Пункты выбранного вида контроля."""
        return [item for item in DeadlineService().collect(now=self.now) if item.notify_type == kind]

    def set_rule(self, kind: str, **values) -> None:
        """Меняет строку NotifySettings."""
        NotifySettings.objects.filter(notify_type=kind).update(**values)


class ActionDeadlineTest(DeadlineServiceTestCase):
    """Просрочки и предупреждения по действиям."""

    def test_overdue_action_goes_to_responsible(self) -> None:
        """Просроченное действие — пункт overdue для ответственного с описанием."""
        instance = self.action()

        items = self.items(NotifyType.ACTION_DEADLINE)

        # Проверяем, что найден ровно один пункт по действию
        self.assertEqual([item.object_id for item in items], [instance.pk])
        # Проверяем событие, срок и получателя
        self.assertEqual(items[0].event, NotifyEvent.OVERDUE)
        self.assertEqual(items[0].deadline, instance.planned_end)
        self.assertEqual(items[0].recipients, (self.kam,))
        # Проверяем описание пункта
        self.assertEqual(items[0].counterparty, str(self.interaction.organization))
        self.assertEqual(items[0].stage_name, self.stage.stage.name)
        self.assertEqual(items[0].action_name, instance.action_name_snapshot)
        # Проверяем id взаимодействия и процесса — из них строится ссылка в колокольчике
        self.assertEqual(items[0].interaction_id, self.interaction.pk)
        self.assertEqual(items[0].workflow_instance_id, self.process.pk)

    def test_not_overdue_and_excluded_actions(self) -> None:
        """Не попадают: срок впереди, выполнено, без длительности, ждёт запуска."""
        self.action(planned_end=self.now + timedelta(days=1))
        self.action(status=ActionInstanceStatus.COMPLETED)
        self.action(duration=None)
        self.action(action__is_trigger_only=True, triggered_at=None)

        # Проверяем, что пунктов нет
        self.assertEqual(self.items(NotifyType.ACTION_DEADLINE), [])

    def test_triggered_trigger_only_action_is_controlled(self) -> None:
        """Запущенное trigger-only действие контролируется как обычное."""
        instance = self.action(action__is_trigger_only=True, triggered_at=self.now - timedelta(days=3))

        # Проверяем, что пункт есть
        self.assertEqual([item.object_id for item in self.items(NotifyType.ACTION_DEADLINE)], [instance.pk])

    def test_action_of_not_running_context_is_skipped(self) -> None:
        """Этап не в работе, процесс завершён или взаимодействие неактивно — контроля нет."""
        pending_stage = StageInstanceFactory(workflow_instance=self.process, status=StageInstanceStatus.PENDING)
        self.action(stage_instance=pending_stage)
        finished = WorkflowInstanceFactory(status=WorkflowInstanceStatus.COMPLETED)
        self.action(stage_instance=StageInstanceFactory(workflow_instance=finished))
        inactive = WorkflowInstanceFactory(interaction=InteractionFactory(is_active=False))
        self.action(stage_instance=StageInstanceFactory(workflow_instance=inactive))

        # Проверяем, что пунктов нет
        self.assertEqual(self.items(NotifyType.ACTION_DEADLINE), [])

    def test_pool_action_goes_to_all_kams(self) -> None:
        """Действие без ответственного (пул) — письмо всем действующим КАМам взаимодействия."""
        second = UserFactory()
        ResponsibleFactory(interaction=self.interaction, manager=second, assigned_by=self.head)
        self.action(responsible=None)

        # Проверяем получателей
        self.assertEqual(self.items(NotifyType.ACTION_DEADLINE)[0].recipients, (self.kam, second))

    def test_pool_action_without_kams_goes_to_head(self) -> None:
        """Действие без ответственного и без КАМов — по умолчанию письмо всем руководителям."""
        Responsible.objects.filter(interaction=self.interaction).update(unassigned_at=self.now)
        self.action(responsible=None)

        # Проверяем получателя
        self.assertEqual(self.items(NotifyType.ACTION_DEADLINE)[0].recipients, (self.head,))

    def test_owned_action_goes_only_to_its_responsible(self) -> None:
        """У действия есть ответственный — второй КАМ взаимодействия письмо не получает."""
        ResponsibleFactory(interaction=self.interaction, manager=UserFactory(), assigned_by=self.head)
        self.action()

        # Проверяем получателя
        self.assertEqual(self.items(NotifyType.ACTION_DEADLINE)[0].recipients, (self.kam,))

    def test_reminder_window(self) -> None:
        """Предупреждение — только в окне remind_before_days до срока."""
        self.set_rule(NotifyType.ACTION_DEADLINE, remind_before_days=2)
        inside = self.action(planned_end=self.now + timedelta(days=1))
        self.action(planned_end=self.now + timedelta(days=3))

        items = self.items(NotifyType.ACTION_DEADLINE)

        # Проверяем, что предупреждение только по действию внутри окна
        self.assertEqual([(item.object_id, item.event) for item in items], [(inside.pk, NotifyEvent.REMINDER)])

    def test_reminder_disabled_by_default(self) -> None:
        """Без remind_before_days предупреждений нет."""
        self.action(planned_end=self.now + timedelta(hours=1))

        # Проверяем, что пунктов нет
        self.assertEqual(self.items(NotifyType.ACTION_DEADLINE), [])

    def test_disabled_rule_or_no_recipients_gives_no_items(self) -> None:
        """Выключенное правило и пункт без получателей не попадают в выборку."""
        self.action()
        self.set_rule(NotifyType.ACTION_DEADLINE, is_enabled=False)

        # Проверяем выключенное правило
        self.assertEqual(self.items(NotifyType.ACTION_DEADLINE), [])

        self.set_rule(NotifyType.ACTION_DEADLINE, is_enabled=True, is_notify_responsible=False, is_notify_head=False)

        # Проверяем правило без получателей
        self.assertEqual(self.items(NotifyType.ACTION_DEADLINE), [])

    def test_missing_rule_row_disables_kind(self) -> None:
        """Удалённая строка NotifySettings выключает вид контроля с предупреждением в лог."""
        self.action()
        NotifySettings.objects.filter(notify_type=NotifyType.ACTION_DEADLINE).delete()

        with self.assertLogs("django", level="WARNING"):
            items = self.items(NotifyType.ACTION_DEADLINE)

        # Проверяем, что пунктов нет
        self.assertEqual(items, [])


class StageDeadlineTest(DeadlineServiceTestCase):
    """Просрочки этапов."""

    def test_stage_deadline_is_latest_action_end(self) -> None:
        """Срок этапа — максимум planned_end действий; получатели — КАМ и руководитель."""
        self.action(planned_end=self.now - timedelta(days=3))
        latest = self.action(planned_end=self.now - timedelta(days=1))

        items = self.items(NotifyType.STAGE_DEADLINE)

        # Проверяем пункт этапа и его срок
        self.assertEqual([item.object_id for item in items], [self.stage.pk])
        self.assertEqual(items[0].deadline, latest.planned_end)
        # Проверяем получателей по умолчанию для этапа
        self.assertEqual(items[0].recipients, (self.kam, self.head))

    def test_stage_deadline_goes_to_all_kams(self) -> None:
        """Срок этапа — письмо всем действующим КАМам взаимодействия и руководителю."""
        second = UserFactory()
        ResponsibleFactory(interaction=self.interaction, manager=second, assigned_by=self.head)
        self.action()

        # Проверяем получателей
        self.assertEqual(self.items(NotifyType.STAGE_DEADLINE)[0].recipients, (self.kam, second, self.head))

    def test_stage_is_not_overdue_while_any_action_ends_later(self) -> None:
        """Этап не просрочен, пока хоть одно действие заканчивается в будущем."""
        self.action(planned_end=self.now - timedelta(days=3))
        self.action(planned_end=self.now + timedelta(days=1))

        # Проверяем, что пункта этапа нет
        self.assertEqual(self.items(NotifyType.STAGE_DEADLINE), [])

    def test_stage_without_any_duration_is_not_controlled(self) -> None:
        """Этап без единого default_duration_days не контролируется."""
        self.action(duration=None)

        # Проверяем, что пункта этапа нет
        self.assertEqual(self.items(NotifyType.STAGE_DEADLINE), [])

    def test_not_triggered_action_does_not_extend_stage(self) -> None:
        """Незапущенное trigger-only действие не сдвигает срок этапа."""
        self.action(planned_end=self.now - timedelta(days=1))
        self.action(planned_end=self.now + timedelta(days=5), action__is_trigger_only=True, triggered_at=None)

        # Проверяем, что этап просрочен
        self.assertEqual(len(self.items(NotifyType.STAGE_DEADLINE)), 1)


class WorkflowDeadlineTest(DeadlineServiceTestCase):
    """SLA процесса целиком."""

    def set_started(self, days_ago: int) -> None:
        """Сдвигает начало процесса (auto_now_add не даёт задать его при создании)."""
        WorkflowInstance.objects.filter(pk=self.process.pk).update(started_at=self.now - timedelta(days=days_ago))

    def test_workflow_over_sla(self) -> None:
        """Процесс дольше stale_threshold_days — пункт с КАМом и руководителем."""
        self.process.workflow.stale_threshold_days = 10
        self.process.workflow.save(update_fields=["stale_threshold_days"])
        self.set_started(days_ago=11)

        items = self.items(NotifyType.WORKFLOW_DEADLINE)

        # Проверяем пункт процесса и получателей
        self.assertEqual([item.object_id for item in items], [self.process.pk])
        self.assertEqual(items[0].workflow_name, self.process.workflow.name)
        self.assertEqual(items[0].recipients, (self.kam, self.head))

    def test_workflow_without_sla_or_completed_is_skipped(self) -> None:
        """Без stale_threshold_days или завершённый процесс не контролируется."""
        self.set_started(days_ago=400)

        # Проверяем процесс без SLA
        self.assertEqual(self.items(NotifyType.WORKFLOW_DEADLINE), [])

        self.process.workflow.stale_threshold_days = 10
        self.process.workflow.save(update_fields=["stale_threshold_days"])
        WorkflowInstance.objects.filter(pk=self.process.pk).update(status=WorkflowInstanceStatus.COMPLETED)

        # Проверяем завершённый процесс
        self.assertEqual(self.items(NotifyType.WORKFLOW_DEADLINE), [])
