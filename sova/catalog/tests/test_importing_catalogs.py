from django.test import TestCase

from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.models import ContactPerson, Product, Program, Vendor
from sova.catalog.services import catalog_import_service
from sova.catalog.tests.factories import DirectionFactory, UniversityFactory


class LoadVendorsServiceTestCase(TestCase):
    """load_vendors — вызывается напрямую, без Command/CommandError/stdout."""

    def test_returns_created_and_updated_counts(self) -> None:
        rows = iter([(2, {"name": "Вендор", "external_code": "vendor-1"})])

        created, updated = catalog_import_service.load_vendors(rows)

        self.assertEqual((created, updated), (1, 0))
        self.assertTrue(Vendor.objects.filter(external_code="vendor-1").exists())

    def test_raises_domain_error_on_missing_name(self) -> None:
        rows = iter([(2, {"external_code": "vendor-1"})])

        with self.assertRaises(CatalogImportError):
            catalog_import_service.load_vendors(rows)


class LoadContactPersonsTestCase(TestCase):
    """load_contact_persons — апсерт ответственных от вуза по (university, full_name)."""

    def test_creates_and_updates_contact_person(self) -> None:
        university = UniversityFactory(name="МГУ")
        rows = iter(
            [
                (2, {"full_name": "Иванов Иван", "university": "МГУ", "email": "ivanov@example.com"}),
            ]
        )

        created, updated = catalog_import_service.load_contact_persons(rows)

        self.assertEqual((created, updated), (1, 0))
        contact = ContactPerson.objects.get(university=university, full_name="Иванов Иван")
        self.assertEqual(contact.email, "ivanov@example.com")

    def test_unknown_university_raises(self) -> None:
        rows = iter([(2, {"full_name": "Иванов Иван", "university": "Неизвестный вуз"})])

        with self.assertRaises(CatalogImportError):
            catalog_import_service.load_contact_persons(rows)


class CollectRowErrorsTestCase(TestCase):
    """Ошибки собираются по всем строкам файла, а импорт откатывается целиком."""

    def test_collects_errors_from_all_rows_and_saves_nothing(self) -> None:
        rows = iter(
            [
                (2, {"name": "Вендор", "external_code": "vendor-1"}),
                (3, {"external_code": "vendor-2"}),
                (4, {"name": "Вендор 3", "external_code": "vendor-3", "is_active": "может быть"}),
            ]
        )

        with self.assertRaises(CatalogImportRowsError) as context:
            catalog_import_service.load_vendors(rows)

        self.assertEqual([error.row_number for error in context.exception.errors], [3, 4])
        self.assertEqual(context.exception.errors[0].message, "поле name обязательно")
        self.assertIn("Строка 3: поле name обязательно", str(context.exception))
        self.assertFalse(Vendor.objects.exists())

    def test_lookup_error_is_reported_with_row_number(self) -> None:
        UniversityFactory(name="МГУ")
        rows = iter(
            [
                (2, {"full_name": "Иванов Иван", "university": "МГУ"}),
                (3, {"full_name": "Петров Пётр", "university": "Неизвестный вуз"}),
            ]
        )

        with self.assertRaises(CatalogImportRowsError) as context:
            catalog_import_service.load_contact_persons(rows)

        [error] = context.exception.errors
        self.assertEqual((error.row_number, error.message), (3, "вуз не найден: Неизвестный вуз"))
        self.assertFalse(ContactPerson.objects.exists())


class CaseInsensitiveMatchingTestCase(TestCase):
    """Импорт сопоставляет записи без учёта регистра; файл справочника перезаписывает написание."""

    def test_catalog_file_updates_record_found_in_other_case_and_overwrites_name(self) -> None:
        Vendor.objects.create(name="яНДЕКС")

        created, updated = catalog_import_service.load_vendors(iter([(2, {"name": "Яндекс", "external_code": None})]))

        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(Vendor.objects.get().name, "Яндекс")

    def test_code_is_matched_in_other_case(self) -> None:
        Product.objects.create(name="Docker", external_code="P-001")
        rows = iter([(2, {"name": "Docker Desktop", "external_code": "p-001", "vendor": None})])

        created, updated = catalog_import_service.load_products(rows)

        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(Product.objects.get().name, "Docker Desktop")

    def test_reference_is_found_in_other_case_and_not_renamed(self) -> None:
        vendor = Vendor.objects.create(name="яНДЕКС")
        rows = iter([(2, {"name": "Облако", "external_code": "p-1", "vendor": "Яндекс"})])

        catalog_import_service.load_products(rows)

        self.assertEqual(Product.objects.get().vendor_id, vendor.id)
        self.assertEqual(Vendor.objects.get().name, "яНДЕКС")

    def test_program_is_matched_by_name_in_other_case(self) -> None:
        direction = DirectionFactory(name="DevOps")
        Program.objects.create(name="DevOps-инженер", direction=direction)

        created, updated = catalog_import_service.load_programs(
            iter([(2, {"name": "devops-ИНЖЕНЕР", "direction": "devops"})])
        )

        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(Program.objects.get().name, "devops-ИНЖЕНЕР")

    def test_contact_person_is_matched_in_other_case(self) -> None:
        university = UniversityFactory(name="МГУ")
        ContactPerson.objects.create(full_name="Иванов Иван", university=university)
        rows = iter([(2, {"full_name": "ИВАНОВ ИВАН", "university": "мгу", "email": "ivanov@example.com"})])

        created, updated = catalog_import_service.load_contact_persons(rows)

        self.assertEqual((created, updated), (0, 1))
        contact = ContactPerson.objects.get()
        self.assertEqual((contact.full_name, contact.email), ("ИВАНОВ ИВАН", "ivanov@example.com"))
