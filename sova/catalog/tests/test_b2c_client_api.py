from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import B2CClientFactory
from sova.core.tests.factories import UserFactory


class B2CClientInnPhoneValidationTestCase(APITestCase):
    """ИНН и телефон B2C-клиента: только допустимые символы, понятное сообщение об ошибке."""

    def setUp(self) -> None:
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=user)

    def test_create_with_valid_inn_and_phone(self) -> None:
        response = self.client.post(
            reverse("catalog:b2c-client-list"),
            {"full_name": "Иванов Иван", "inn": "500100732259", "phone": "+7 (999) 123-45-67"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.json())

    def test_create_rejects_inn_with_letters(self) -> None:
        response = self.client.post(
            reverse("catalog:b2c-client-list"),
            {"full_name": "Иванов Иван", "inn": "50010073225a"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["inn"], ["ИНН должен состоять из 10 или 12 цифр."])

    def test_create_rejects_inn_of_wrong_length(self) -> None:
        response = self.client.post(
            reverse("catalog:b2c-client-list"),
            {"full_name": "Иванов Иван", "inn": "12345678901"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("inn", response.json())

    def test_create_rejects_too_long_inn_with_single_message(self) -> None:
        """Слишком длинный ИНН — одно понятное сообщение, без стандартного «не более 12 символов»."""
        response = self.client.post(
            reverse("catalog:b2c-client-list"),
            {"full_name": "Иванов Иван", "inn": "1234567890123"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["inn"], ["ИНН должен состоять из 10 или 12 цифр."])

    def test_update_rejects_phone_with_letters(self) -> None:
        b2c_client = B2CClientFactory()

        response = self.client.patch(
            reverse("catalog:b2c-client-detail", args=(b2c_client.pk,)),
            {"phone": "+7 999 abc-45-67"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json())
