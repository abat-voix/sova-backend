import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.integrations.models import IntegrationMapping
from sova.training.models import TrainingApplicationLearner, TrainingStream

PAYMENTS_FILE = Path(settings.BASE_DIR) / "docs" / "Хакатон" / "Данные оплат.json"


class TrainingPaymentJsonImportTest(APITestCase):
    """«Данные оплат.json» через входящий маппинг интеграции «Оплата обучения»."""

    def setUp(self):
        self.output = Path(tempfile.mkdtemp()) / "payments.json"
        call_command("load_training_payment_demo", file=str(PAYMENTS_FILE), output=str(self.output), stdout=None)
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
        data = self.process(json.loads(PAYMENTS_FILE.read_text(encoding="utf-8")))
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
