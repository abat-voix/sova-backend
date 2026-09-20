import json
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from sova.catalog.models import Product, University, Vendor
from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.interactions.models import Interaction
from sova.processes.demo.scenarios import SCENARIOS, Progress, run_steps
from sova.processes.demo.seed import make_transport, seed_demo_data
from sova.processes.models import ActionAttachment, WorkflowInstance
from sova.workflows.models import ActionOutcome, Workflow

DEMO_WORKFLOW_CODES = {"demo-linear", "demo-branching", "demo-products", "demo-rollback", "demo-rules", "demo-empty"}
PDF = b"%PDF-1.4\n%%EOF\n"


class SeedDemoDataTestCase(TemporaryMediaMixin, TestCase):
    """Тесты команды `seed_demo_data`: создаёт всё, из чего запускаются сценарии ручной проверки."""

    def setUp(self) -> None:
        """Суперпользователь, от имени которого команда создаёт данные."""
        self.admin = UserFactory(is_staff=True, is_superuser=True)

    def call(self, *args: str) -> str:
        """Вызывает команду и возвращает то, что она напечатала."""
        out = StringIO()
        call_command("seed_demo_data", *args, stdout=out)
        return out.getvalue()

    def run_execution_steps(self, progress: Progress) -> None:
        """Выполняет часть «выполнение» всех сценариев поверх созданных командой данных."""
        client = APIClient(SERVER_NAME="localhost")
        client.force_authenticate(user=self.admin)

        def send(method, path, body, files):
            if files:
                data = {**(body or {})}
                for name in files:
                    data[name] = SimpleUploadedFile("act.pdf", PDF, content_type="application/pdf")
                response = client.post(path=path, data=data, format="multipart")
            else:
                response = getattr(client, method.lower())(path=path, data=body, format="json")
            return response.status_code, (json.loads(response.content) if response.content else None)

        for scenario in SCENARIOS.values():
            run_steps(scenario.steps, send, progress.variables)

    def test_command_creates_catalog_definitions_and_interactions(self) -> None:
        """Создаются справочники, все демо-workflow и взаимодействия для сценариев; процессы не запускаются."""
        self.call()

        # Проверяем справочники
        self.assertTrue(University.objects.filter(name="Демо-университет").exists())
        self.assertTrue(Vendor.objects.filter(name="Демо-вендор").exists())
        self.assertEqual(Product.objects.filter(name__startswith="Демо-ПО").count(), 3)
        # Проверяем workflow и взаимодействия
        self.assertEqual(set(Workflow.objects.values_list("code", flat=True)), DEMO_WORKFLOW_CODES)
        self.assertEqual(Interaction.objects.count(), 8)
        # Проверяем, что процессы оставлены пользователю
        self.assertFalse(WorkflowInstance.objects.exists())

    def test_definitions_are_created_through_the_api_with_its_rules(self) -> None:
        """Определения создаются через API: у действий есть исходы «Выполнено», а сценарий 2 получает свои исходы."""
        self.call()

        # Проверяем исходы
        self.assertLessEqual({"done", "needs_fix", "retry"}, set(ActionOutcome.objects.values_list("code", flat=True)))

    def test_output_lists_values_and_the_first_execution_step_of_each_scenario(self) -> None:
        """Вывод содержит id для подстановки и первый шаг выполнения каждого сценария."""
        output = self.call()

        workflow = Workflow.objects.get(code="demo-linear")
        interaction = Interaction.objects.get(comment="Сценарий 1")
        # Проверяем значения и подсказку по запуску
        self.assertIn(str(workflow.pk), output)
        self.assertIn(str(interaction.pk), output)
        self.assertIn("POST /api/processes/workflow-instances/", output)
        self.assertIn("1.17", output)

    def test_http_option_prints_variables_for_http_client(self) -> None:
        """Ключ --http печатает значения в виде `@имя = значение` для файла HTTP-клиента."""
        output = self.call("--http")

        workflow = Workflow.objects.get(code="demo-linear")
        # Проверяем строку переменной
        self.assertIn(f"@wf1 = {workflow.pk}", output)

    def test_prepared_data_is_enough_to_execute_every_scenario(self) -> None:
        """Подготовка + выполнение равны полному сценарию: после команды все шаги выполнения проходят."""
        progress = seed_demo_data(transport=make_transport(user=self.admin))

        # Проверяем, что все сценарии выполняются без расхождений
        self.run_execution_steps(progress)
        self.assertTrue(WorkflowInstance.objects.exists())

    def test_second_run_without_reset_is_refused(self) -> None:
        """Повторный запуск без --reset отказывает и ничего не меняет."""
        self.call()
        workflows_before = Workflow.objects.count()

        # Проверяем отказ с подсказкой
        with self.assertRaisesMessage(CommandError, "--reset"):
            self.call()
        self.assertEqual(Workflow.objects.count(), workflows_before)

    def test_reset_recreates_data_and_removes_processes_and_attachments(self) -> None:
        """--reset удаляет демо-данные вместе с процессами и загруженными файлами и создаёт их заново."""
        progress = seed_demo_data(transport=make_transport(user=self.admin))
        self.run_execution_steps(progress)
        self.assertTrue(ActionAttachment.objects.exists())
        old_workflow = Workflow.objects.get(code="demo-linear")

        self.call("--reset")

        # Проверяем, что процессы и вложения удалены, а данные созданы заново
        self.assertFalse(WorkflowInstance.objects.exists())
        self.assertFalse(ActionAttachment.objects.exists())
        self.assertEqual(set(Workflow.objects.values_list("code", flat=True)), DEMO_WORKFLOW_CODES)
        self.assertNotEqual(Workflow.objects.get(code="demo-linear").pk, old_workflow.pk)
        self.assertEqual(Interaction.objects.count(), 8)

    def test_reset_keeps_foreign_data(self) -> None:
        """--reset не трогает данные, не относящиеся к демо."""
        foreign = Vendor.objects.create(name="Чужой вендор")
        self.call()

        self.call("--reset")

        # Проверяем, что чужие данные на месте
        self.assertTrue(Vendor.objects.filter(pk=foreign.pk).exists())

    def test_command_requires_a_superuser(self) -> None:
        """Без суперпользователя команда подсказывает, как его создать."""
        self.admin.delete()

        # Проверяем сообщение
        with self.assertRaisesMessage(CommandError, "createsuperuser"):
            self.call()

    def test_username_option_selects_the_author(self) -> None:
        """Ключ --username задаёт автора; неизвестный пользователь отвергается."""
        other = UserFactory(is_staff=True, is_superuser=True)

        self.call("--username", other.get_username())
        # Проверяем, что автор аудита — выбранный пользователь
        from sova.workflows.models import WorkflowChange

        self.assertEqual(set(WorkflowChange.objects.values_list("created_by", flat=True)), {other.pk})
        with self.assertRaisesMessage(CommandError, "не найден"):
            self.call("--username", "nobody", "--reset")

    @override_settings(ENVIRONMENT="production")
    def test_command_refuses_to_run_outside_development_without_force(self) -> None:
        """Вне разработки команда требует --force."""
        # Проверяем отказ и то, что с --force команда работает
        with self.assertRaisesMessage(CommandError, "--force"):
            self.call()
        self.assertFalse(Workflow.objects.exists())
        self.call("--force")
        self.assertTrue(Workflow.objects.exists())
