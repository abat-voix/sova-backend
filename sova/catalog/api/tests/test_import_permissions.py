from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.enum import CatalogType
from sova.catalog.tests.factories import CatalogImportMappingFactory
from sova.core.tests.factories import UserFactory

_NON_ADMIN_ROLES = (SystemRole.OBSERVER, SystemRole.KAM, SystemRole.HEAD)


class CatalogImportPermissionsApiTestCase(APITestCase):
    """Импорт каталогов и маппинги импорта доступны только администратору платформы."""

    def setUp(self) -> None:
        """Маппинг, на котором проверяется retrieve."""
        self.mapping = CatalogImportMappingFactory(catalog_type=CatalogType.VENDOR, target_field="name")

    def _authenticate(self, role: str) -> None:
        user = UserFactory()
        UserRole.objects.create(user=user, role=role)
        self.client.force_authenticate(user=user)

    def _requests(self) -> dict:
        """Запросы ко всем эндпоинтам импорта: имя → вызов клиента."""
        by_type = reverse("catalog:import-mapping-by-type", args=[CatalogType.VENDOR])
        return {
            "mappings list": lambda: self.client.get(reverse("catalog:import-mapping-list")),
            "mappings retrieve": lambda: self.client.get(
                reverse("catalog:import-mapping-detail", args=[self.mapping.pk])
            ),
            "mappings fields": lambda: self.client.get(
                reverse("catalog:import-mapping-fields"), data={"catalog_type": CatalogType.VENDOR}
            ),
            "mapping by type GET": lambda: self.client.get(by_type),
            "mapping by type PUT": lambda: self.client.put(
                by_type, data={"mappings": {"name": "Вендор"}}, format="json"
            ),
            "headers": lambda: self.client.post(
                reverse("catalog:catalog-import-headers"), data={}, format="multipart"
            ),
            "import": lambda: self.client.post(
                reverse("catalog:catalog-import-list"), data={"catalog_type": CatalogType.VENDOR}, format="multipart"
            ),
        }

    def test_non_admin_roles_are_forbidden(self) -> None:
        """Наблюдатель, КАМ и руководитель получают 403 на любой эндпоинт импорта."""
        for role in _NON_ADMIN_ROLES:
            self._authenticate(role)
            for name, send in self._requests().items():
                with self.subTest(role=role, request=name):
                    # Проверяем, что операция запрещена ролью
                    self.assertEqual(send().status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_admin_is_allowed(self) -> None:
        """Администратор платформы проходит проверку прав (ответ не 403)."""
        self._authenticate(SystemRole.PLATFORM_ADMIN)
        for name, send in self._requests().items():
            with self.subTest(request=name):
                # Проверяем, что права не мешают: 400 на пустую загрузку допустим, 403 — нет
                self.assertNotEqual(send().status_code, status.HTTP_403_FORBIDDEN)
