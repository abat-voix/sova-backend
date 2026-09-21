from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.processes.models import WorkflowInstance
from sova.processes.tests.factories import WorkflowInstanceFactory
from sova.workflows.enum import Audience
from sova.workflows.models import ActionOutcome, Workflow, WorkflowAction, WorkflowStage


class CreateWorkflowTemplateCommandTest(TestCase):
    """Тесты команды `create_workflow_template`: создание шаблона и защита существующего."""

    def run_command(self, *args: str) -> str:
        """Запускает команду и возвращает её вывод."""
        out = StringIO()
        call_command("create_workflow_template", *args, stdout=out)
        return out.getvalue()

    def test_command_creates_base_template(self) -> None:
        """Без аргументов создаётся базовый B2B-шаблон со всем графом."""
        self.run_command()

        workflow = Workflow.objects.get(code="base-b2b")
        # Проверяем аудиторию и то, что шаблон не базовый по умолчанию
        self.assertEqual(workflow.audience, Audience.B2B)
        self.assertFalse(workflow.is_base)
        self.assertTrue(workflow.active)
        # Проверяем, что граф собран
        self.assertEqual(WorkflowStage.objects.filter(workflow=workflow).count(), 5)
        self.assertEqual(WorkflowAction.objects.filter(stage__workflow=workflow).count(), 12)

    def test_command_gives_every_action_at_least_one_outcome(self) -> None:
        """У каждого действия есть исход — иначе его нельзя завершить."""
        self.run_command()

        actions = WorkflowAction.objects.filter(stage__workflow__code="base-b2b")
        without_outcome = [
            action.name for action in actions if not ActionOutcome.objects.filter(action=action).exists()
        ]
        # Проверяем, что действий без исхода нет
        self.assertEqual(without_outcome, [])

    def test_command_reports_what_was_created(self) -> None:
        """Вывод сообщает код шаблона и размер собранного графа."""
        output = self.run_command()

        # Проверяем ключевые числа и код в выводе
        self.assertIn("base-b2b", output)
        self.assertIn("этапов: 5", output)
        self.assertIn("действий: 12", output)

    def test_command_overrides_code_and_name(self) -> None:
        """Код и название шаблона можно задать аргументами."""
        self.run_command("--code=pilot-b2b", "--name=Пилот")

        workflow = Workflow.objects.get(code="pilot-b2b")
        # Проверяем переопределённые поля
        self.assertEqual(workflow.name, "Пилот")
        self.assertFalse(Workflow.objects.filter(code="base-b2b").exists())

    def test_command_marks_template_as_base_on_request(self) -> None:
        """С `--base` шаблон становится базовым для своей аудитории."""
        self.run_command("--base")

        # Проверяем флаг базового шаблона
        self.assertTrue(Workflow.objects.get(code="base-b2b").is_base)

    def test_command_sets_author_from_username(self) -> None:
        """С `--username` автором шаблона становится указанный пользователь."""
        user = UserFactory()

        self.run_command(f"--username={user.username}")

        # Проверяем автора шаблона
        self.assertEqual(Workflow.objects.get(code="base-b2b").created_by, user)

    def test_command_rejects_unknown_username(self) -> None:
        """Неизвестный пользователь останавливает команду до создания шаблона."""
        with self.assertRaisesMessage(CommandError, "somebody"):
            self.run_command("--username=somebody")

        # Проверяем, что шаблон не создан
        self.assertFalse(Workflow.objects.filter(code="base-b2b").exists())

    def test_command_refuses_existing_code(self) -> None:
        """Повторный запуск не трогает существующий шаблон и подсказывает про `--recreate`."""
        self.run_command()
        existing = Workflow.objects.get(code="base-b2b")

        with self.assertRaisesMessage(CommandError, "--recreate"):
            self.run_command()

        # Проверяем, что шаблон остался прежним и единственным
        self.assertEqual([workflow.pk for workflow in Workflow.objects.all()], [existing.pk])

    def test_recreate_replaces_existing_template(self) -> None:
        """С `--recreate` старый шаблон удаляется и собирается заново."""
        self.run_command()
        existing = Workflow.objects.get(code="base-b2b")

        self.run_command("--recreate")

        # Проверяем, что шаблон один и это новый объект
        workflows = Workflow.objects.filter(code="base-b2b")
        self.assertEqual(workflows.count(), 1)
        self.assertNotEqual(workflows.first().pk, existing.pk)

    def test_recreate_refuses_template_with_started_processes(self) -> None:
        """Пересоздание шаблона с запущенными процессами запрещено: каскад снёс бы их историю."""
        self.run_command()
        workflow = Workflow.objects.get(code="base-b2b")
        WorkflowInstanceFactory(workflow=workflow)

        with self.assertRaisesMessage(CommandError, "процесс"):
            self.run_command("--recreate")

        # Проверяем, что шаблон и процесс на месте
        self.assertTrue(Workflow.objects.filter(pk=workflow.pk).exists())
        self.assertEqual(WorkflowInstance.objects.filter(workflow=workflow).count(), 1)

    def test_command_creates_template_for_b2c_audience(self) -> None:
        """Аудиторию шаблона можно сменить, не меняя граф."""
        self.run_command("--audience=b2c", "--code=base-b2c")

        workflow = Workflow.objects.get(code="base-b2c")
        # Проверяем аудиторию и сохранённый граф
        self.assertEqual(workflow.audience, Audience.B2C)
        self.assertEqual(WorkflowStage.objects.filter(workflow=workflow).count(), 5)
