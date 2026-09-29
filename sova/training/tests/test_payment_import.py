import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.integrations.models import IntegrationMapping
from sova.training.models import TrainingApplicationLearner, TrainingStream

PAYMENTS = [
    None,
    {"Курс": "Анализ данных", "Фамилия": "Петрова", "Имя": "Анна", "Отчество": "Сергеевна",
     "Телефон": "7 (999) 000-00-01", "Email": "petrova@test.ru", "Номер потока": 1},
    {"Курс": "Инженер-тестировщик", "Фамилия": "Сидоров", "Имя": "Максим", "Отчество": "Олегович",
     "Телефон": "7 (999) 000-00-02", "Email": "sidorov@test.ru", "Номер потока": 1},
    {"Курс": "Управление ИТ-проектами", "Фамилия": "Козлов", "Имя": "Илья", "Отчество": "Петрович",
     "Телефон": "7 (999) 000-00-03", "Email": "kozlov@test.ru", "Номер потока": 2},
    {"Курс": "Промпт-инжиниринг", "Фамилия": "Орлова", "Имя": "Ирина", "Отчество": "Викторовна",
     "Телефон": "7 (999) 000-00-04", "Email": "orlova@test.ru", "Номер потока": 3},
    {"Курс": "Python-разработчик", "Фамилия": "Иванов", "Имя": "Михаил", "Отчество": "Петрович",
     "Телефон": "7 (999) 000-00-05", "Email": "ivanov@test.ru", "Номер потока": 4},
]


class TrainingPaymentJsonImportTest(APITestCase):
    """JSON оплат через входящий маппинг интеграции «Оплата обучения»."""

    def setUp(self):
        directory = Path(tempfile.mkdtemp())
        source = directory / "source.json"
        source.write_text(json.dumps(PAYMENTS, ensure_ascii=False), encoding="utf-8")
        self.output = directory / "payments.json"
        call_command("load_training_payment_demo", file=str(source), output=str(self.output), stdout=None)
        self.mapping = IntegrationMapping.objects.get(entity="training_payment")
        admin = get_user_model().objects.create_user(username="payments-admin", password="test")
        UserRole.objects.create(user=admin, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(admin)

    def process(self, payload):
        response = self.client.post(
            reverse("integrations:mapping-process", args=[self.mapping.pk]), {"payload": payload}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_demo_data_matches_file(self):
        self.assertEqual(TrainingStream.objects.count(), 5)
        self.assertEqual(TrainingApplicationLearner.objects.filter(is_paid=False).count(), 5)
        self.assertTrue(self.mapping.is_active)

    def test_payments_mark_all_learners_paid(self):
        data = self.process(json.loads(self.output.read_text(encoding="utf-8")))
        self.assertEqual(data["status"], "processed", data["errors"])
        self.assertEqual(len(data["created"]), 5)
        self.assertEqual(data["warnings"], ["Элемент 1: пустой элемент пропущен"])
        self.assertFalse(TrainingApplicationLearner.objects.filter(is_paid=False).exists())

    def test_repeated_upload_is_idempotent(self):
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        self.process(payload)
        self.assertEqual(self.process(payload)["status"], "processed")

    def test_original_file_stream_numbers_are_not_stream_ids(self):
        data = self.process(PAYMENTS)
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["created"], [])
        self.assertIn("Элемент 2: non_field_errors: Поток не найден: 1.", data["errors"])
        self.assertFalse(TrainingApplicationLearner.objects.filter(is_paid=True).exists())

    def test_rows_are_processed_independently(self):
        payload = json.loads(self.output.read_text(encoding="utf-8"))
        payload[2]["Курс"] = "Неизвестный курс"
        data = self.process(payload)
        self.assertEqual(data["status"], "failed")
        self.assertEqual(len(data["created"]), 4)
        self.assertEqual(len(data["errors"]), 1)
        self.assertTrue(data["errors"][0].startswith("Элемент 3:"))
        self.assertEqual(TrainingApplicationLearner.objects.filter(is_paid=True).count(), 4)
