import json
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.processes.demo.scenario_docs import render_http, render_markdown
from sova.processes.demo.scenarios import SCENARIOS, run_scenario

PDF = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n<< >>\n%%EOF\n"


class ScenarioTestCase(TemporaryMediaMixin, APITestCase):
    """
    Сценарии ручной проверки исполняются как есть: те же запросы, ожидания и сохранение значений.

    Если тест упал, инструкция в `docs/manual-testing/` описывает поведение, которого нет (или наоборот).
    """

    def setUp(self) -> None:
        """Аутентифицирует клиента суперпользователем, как при ручной проверке."""
        self.client.force_authenticate(user=UserFactory(is_staff=True, is_superuser=True))

    def send(self, method: str, path: str, body: dict | None, files: dict | None) -> tuple[int, object]:
        """Отправляет запрос сценария через тестовый клиент и возвращает код и JSON ответа."""
        if files:
            data = {**(body or {})}
            for field_name in files:
                data[field_name] = SimpleUploadedFile("act.pdf", PDF, content_type="application/pdf")
            response = self.client.post(path=path, data=data, format="multipart")
        else:
            response = getattr(self.client, method.lower())(path=path, data=body, format="json")
        return response.status_code, (json.loads(response.content) if response.content else None)

    def run_key(self, key: str) -> dict:
        """Выполняет сценарий (подготовку и выполнение) и возвращает сохранённые значения."""
        return run_scenario(key, self.send).variables

    def test_setup(self) -> None:
        """Подготовка данных выполняется."""
        # Проверяем, что справочники созданы
        self.assertIn("university", self.run_key("setup"))

    def test_linear(self) -> None:
        """Сценарий 1: линейный путь."""
        # Проверяем, что процесс завершён
        self.assertIn("process_1", self.run_key("linear"))

    def test_branching(self) -> None:
        """Сценарий 2: ветвление по исходам."""
        # Проверяем, что оба процесса запущены
        variables = self.run_key("branching")
        self.assertIn("process_2b", variables)

    def test_products(self) -> None:
        """Сценарий 3: программы и продукты."""
        # Проверяем, что процесс завершён
        self.assertIn("process_3", self.run_key("products"))

    def test_late_product(self) -> None:
        """Сценарий 3б: продукт, добавленный после запуска."""
        # Проверяем, что сценарий выполнен
        self.assertIn("process_3b", self.run_key("late_product"))

    def test_rollback(self) -> None:
        """Сценарий 4: откат."""
        # Проверяем, что сценарий выполнен
        self.assertIn("process_4", self.run_key("rollback"))

    def test_rollback_products(self) -> None:
        """Сценарий 4б: откат этапа продукта."""
        # Проверяем, что сценарий выполнен
        self.assertIn("process_4b", self.run_key("rollback_products"))

    def test_rules(self) -> None:
        """Сценарий 5: правила и ошибки."""
        # Проверяем, что сценарий выполнен
        self.assertIn("process_5", self.run_key("rules"))

    def test_every_scenario_has_a_test(self) -> None:
        """Каждый описанный сценарий покрыт тестом выше."""
        covered = {"setup", "linear", "branching", "products", "late_product", "rollback", "rollback_products", "rules"}
        # Проверяем, что новый сценарий не остался без теста
        self.assertEqual(set(SCENARIOS), covered)

    def test_generated_documents_are_up_to_date(self) -> None:
        """Инструкция и файл HTTP-клиента соответствуют сценариям; иначе запустите docs/manual-testing/build.py."""
        folder = Path(__file__).resolve().parents[3] / "docs" / "manual-testing"
        # Проверяем, что сгенерированные файлы не устарели
        self.assertEqual((folder / "README.md").read_text(encoding="utf-8"), render_markdown())
        self.assertEqual((folder / "sova-workflow.http").read_text(encoding="utf-8"), render_http())
