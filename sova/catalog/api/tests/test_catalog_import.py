from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook
from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.enum import CatalogType
from sova.catalog.models import Vendor
from sova.catalog.tests.factories import CatalogImportMappingFactory
from sova.core.tests.factories import UserFactory


def _xlsx(name: str, *rows: tuple) -> SimpleUploadedFile:
    """Загружаемый xlsx-файл с заданными строками (первая — заголовки)."""
    workbook = Workbook()
    for row in rows:
        workbook.active.append(row)
    content = BytesIO()
    workbook.save(content)
    return SimpleUploadedFile(name, content.getvalue())


class CatalogImportApiTestCase(APITestCase):
    """Тесты POST /api/catalog/imports/."""

    def setUp(self) -> None:
        """Аутентифицирует клиента и настраивает маппинг вендоров."""
        self.client.force_authenticate(user=UserFactory())
        self.url = reverse("catalog:catalog-import-list")
        CatalogImportMappingFactory(catalog_type=CatalogType.VENDOR, source_column="Вендор", target_field="name")
        CatalogImportMappingFactory(catalog_type=CatalogType.VENDOR, source_column="Код", target_field="external_code")

    def _post(self, catalog_type: str, file: SimpleUploadedFile):
        return self.client.post(
            path=self.url,
            data={"catalog_type": catalog_type, "file": file},
            format="multipart",
        )

    def test_import_returns_counts(self) -> None:
        """Успешный импорт возвращает количество созданных и обновлённых записей."""
        file = _xlsx("vendors.xlsx", ("Вендор", "Код"), ("JetBrains", "jb"), ("1С", "one-c"))

        response = self._post(CatalogType.VENDOR, file)

        # Проверяем ответ и что записи созданы
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data, {"catalog_type": CatalogType.VENDOR, "created": 2, "updated": 0})
        self.assertEqual(Vendor.objects.count(), 2)

    def test_row_errors_return_400_with_error_list(self) -> None:
        """Ошибки строк возвращаются списком с номерами строк, ничего не сохраняется."""
        file = _xlsx("vendors.xlsx", ("Вендор", "Код"), ("JetBrains", "jb"), (None, "no-name"))

        response = self._post(CatalogType.VENDOR, file)

        # Проверяем формат ошибки и откат импорта
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "import_failed")
        self.assertEqual(response.data["errors"], [{"row": 3, "message": "поле name обязательно"}])
        self.assertEqual(response.data["errors_total"], 1)
        self.assertFalse(Vendor.objects.exists())

    def test_error_list_is_limited(self) -> None:
        """В ответе не больше 100 ошибок, errors_total — полное число."""
        rows = [(None, f"code-{index}") for index in range(150)]
        file = _xlsx("vendors.xlsx", ("Вендор", "Код"), *rows)

        response = self._post(CatalogType.VENDOR, file)

        # Проверяем усечение списка ошибок
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(len(response.data["errors"]), 100)
        self.assertEqual(response.data["errors_total"], 150)

    def test_file_level_error_returns_400(self) -> None:
        """Ошибка файла целиком (нет обязательной колонки) возвращает 400 без списка строк."""
        file = _xlsx("vendors.xlsx", ("Вендор",), ("JetBrains",))

        response = self._post(CatalogType.VENDOR, file)

        # Проверяем, что ошибка описана в detail
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "import_error")
        self.assertIn("external_code", response.data["detail"])

    def test_unsupported_extension_returns_400(self) -> None:
        """Файл не xls/xlsx отклоняется валидацией."""
        file = SimpleUploadedFile("vendors.csv", b"name\nJetBrains\n")

        response = self._post(CatalogType.VENDOR, file)

        # Проверяем, что ошибка указывает на file
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_unknown_catalog_type_returns_400(self) -> None:
        """Неизвестный тип каталога отклоняется валидацией."""
        file = _xlsx("vendors.xlsx", ("Вендор", "Код"), ("JetBrains", "jb"))

        response = self._post("unknown", file)

        # Проверяем, что ошибка указывает на catalog_type
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("catalog_type", response.data)

    def test_requires_authentication(self) -> None:
        """Анонимный запрос отклоняется."""
        self.client.force_authenticate(user=None)
        file = _xlsx("vendors.xlsx", ("Вендор", "Код"), ("JetBrains", "jb"))

        response = self._post(CatalogType.VENDOR, file)

        # Проверяем, что доступ запрещён
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
