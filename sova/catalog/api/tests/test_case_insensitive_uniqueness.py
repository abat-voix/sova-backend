from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.models import Vendor
from sova.catalog.tests.factories import (
    ContactPersonFactory,
    ProductFactory,
    UniversityFactory,
    VendorFactory,
)
from sova.core.tests.factories import UserFactory


class CaseInsensitiveUniquenessApiTestCase(APITestCase):
    """Дубли без учёта регистра и невидимых символов отклоняются как 400 с указанием поля, а не 409."""

    def setUp(self) -> None:
        """Аутентифицирует клиента."""
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=user)

    def test_vendor_name_duplicate_in_other_case_returns_400(self) -> None:
        """Вендор «ЯНДЕКС» при существующем «Яндекс» отклоняется."""
        VendorFactory(name="Яндекс")

        response = self.client.post(
            path=reverse("catalog:vendor-list"),
            data={"name": "ЯНДЕКС "},
            format="json",
        )

        # Проверяем, что ошибка привязана к полю name
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_vendor_code_duplicate_in_other_case_returns_400(self) -> None:
        """Код вендора сравнивается без учёта регистра."""
        VendorFactory(external_code="JB")

        response = self.client.post(
            path=reverse("catalog:vendor-list"),
            data={"name": "JetBrains", "external_code": "jb"},
            format="json",
        )

        # Проверяем, что ошибка привязана к полю external_code
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("external_code", response.data)

    def test_vendor_can_change_case_of_own_name(self) -> None:
        """Смена регистра собственного названия — не дубль."""
        vendor = VendorFactory(name="яндекс")

        response = self.client.patch(
            path=reverse("catalog:vendor-detail", args=[vendor.pk]),
            data={"name": "Яндекс"},
            format="json",
        )

        # Проверяем, что сохранено как введено
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(Vendor.objects.get().name, "Яндекс")

    def test_created_value_is_normalized_and_keeps_case(self) -> None:
        """Сохраняется нормализованное значение в регистре, как ввели."""
        response = self.client.post(
            path=reverse("catalog:vendor-list"),
            data={"name": "мОсква  Софт "},
            format="json",
        )

        # Проверяем ответ и сохранённое значение
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["name"], "мОсква Софт")

    def test_university_name_duplicate_in_other_case_returns_400(self) -> None:
        """Вуз «мгу» при существующем «МГУ» отклоняется."""
        UniversityFactory(name="МГУ")

        response = self.client.post(
            path=reverse("catalog:university-list"),
            data={"name": "мгу"},
            format="json",
        )

        # Проверяем, что ошибка привязана к полю name
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_product_name_duplicate_for_vendor_in_other_case_returns_400(self) -> None:
        """Название продукта уникально у вендора без учёта регистра."""
        product = ProductFactory(name="Docker")

        response = self.client.post(
            path=reverse("catalog:product-list"),
            data={"name": "DOCKER", "vendor": str(product.vendor_id)},
            format="json",
        )

        # Проверяем, что ошибка привязана к полю name
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_contact_person_namesakes_are_allowed(self) -> None:
        """ФИО контактного лица не уникально: тёзки — разные люди, пока их явно не свяжут или не сольют."""
        ContactPersonFactory(full_name="Иванов Иван")

        response = self.client.post(
            path=reverse("catalog:contact-person-list"),
            data={"full_name": "ИВАНОВ  ИВАН"},
            format="json",
        )

        # Проверяем, что тёзка создан отдельным человеком
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
