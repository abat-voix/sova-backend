from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.api.root import API_SECTIONS
from sova.core.tests.factories import UserFactory


class ApiRootViewTest(APITestCase):
    """Тесты корня API."""

    def test_returns_links_to_all_sections(self) -> None:
        """Корень отдаёт ссылки на все разделы API."""
        self.client.force_authenticate(user=UserFactory())

        response = self.client.get(reverse("api-root"))

        # Проверяем статус и набор разделов
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data), set(API_SECTIONS))
        # Проверяем, что ссылка ведёт на корень раздела
        self.assertTrue(response.data["catalog"].endswith("/api/catalog/"))

    def test_requires_authentication(self) -> None:
        """Без аутентификации корень недоступен."""
        response = self.client.get(reverse("api-root"))

        # Проверяем отказ в доступе
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
