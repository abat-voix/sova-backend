from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole

from sova.catalog.enum import CatalogType
from sova.catalog.models import Vendor
from sova.catalog.tests.factories import (
    CatalogImportMappingFactory,
    ProductFactory,
    UniversityFactory,
    VendorFactory,
)
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Responsible


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
        self.assertEqual(
            response.data, {"catalog_type": CatalogType.VENDOR, "created": 2, "updated": 0, "warnings": []}
        )
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


class ContractRegistryImportWarningsApiTestCase(APITestCase):
    """Менеджер реестра, не найденный среди КАМов, — предупреждение в ответе, а не ошибка."""

    def setUp(self) -> None:
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.url = reverse("catalog:catalog-import-list")
        columns = {
            "university": "Вуз",
            "vendor": "Вендор",
            "product": "ПО",
            "contract_number": "Номер",
            "manager_full_name": "Менеджер",
        }
        for target_field, source_column in columns.items():
            CatalogImportMappingFactory(
                catalog_type=CatalogType.CONTRACT_REGISTRY, source_column=source_column, target_field=target_field
            )
        UniversityFactory(name="МГУ")
        ProductFactory(name="IDE", vendor=VendorFactory(name="1С"))

    def test_unknown_manager_is_returned_as_warning(self) -> None:
        file = _xlsx(
            "registry.xlsx", ("Вуз", "Вендор", "ПО", "Номер", "Менеджер"), ("МГУ", "1С", "IDE", "Д-1", "Петров Пётр")
        )

        response = self.client.post(
            path=self.url, data={"catalog_type": CatalogType.CONTRACT_REGISTRY, "file": file}, format="multipart"
        )

        # Проверяем, что договор загружен, а по менеджеру — предупреждение со строкой
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(
            response.data["warnings"],
            [
                {
                    "row": 2,
                    "message": (
                        "менеджер Петров Пётр договора Д-1 не назначен: нет КАМа с таким ФИО"
                    ),
                }
            ],
        )

    def test_found_kam_is_assigned_by_uploader(self) -> None:
        kam = UserFactory(first_name="Пётр", last_name="Петров")
        UserRole.objects.create(user=kam, role=SystemRole.KAM)
        file = _xlsx(
            "registry.xlsx", ("Вуз", "Вендор", "ПО", "Номер", "Менеджер"), ("МГУ", "1С", "IDE", "Д-1", "Петров Пётр")
        )

        response = self.client.post(
            path=self.url, data={"catalog_type": CatalogType.CONTRACT_REGISTRY, "file": file}, format="multipart"
        )

        # Проверяем: КАМ назначен договору, автор назначения — загрузивший файл
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        responsible = Responsible.objects.get(contract__contract_number="Д-1")
        self.assertEqual((responsible.manager_id, responsible.assigned_by_id), (kam.pk, self.user.pk))
        self.assertEqual(response.data["warnings"], [])
