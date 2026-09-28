from django.test import TestCase

from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.models import ContactPerson, Direction, Product, Program, Organization, OrganizationContact, Vendor
from sova.catalog.services import catalog_import_service, import_file_service
from sova.catalog.tests.factories import DirectionFactory, OrganizationContactFactory, OrganizationFactory, VendorFactory


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
    """load_contact_persons — человек и его связь с вузом."""

    def test_creates_and_updates_contact_person(self) -> None:
        organization = OrganizationFactory(name="МГУ")
        rows = iter(
            [
                (2, {"full_name": "Иванов Иван", "organization": "МГУ", "email": "ivanov@example.com"}),
            ]
        )

        created, updated = catalog_import_service.load_contact_persons(rows)

        self.assertEqual((created, updated), (1, 0))
        link = OrganizationContact.objects.get(organization=organization, contact__full_name="Иванов Иван")
        self.assertEqual(link.contact.email, "ivanov@example.com")

    def test_unknown_organization_raises(self) -> None:
        rows = iter([(2, {"full_name": "Иванов Иван", "organization": "Неизвестный вуз"})])

        with self.assertRaises(CatalogImportError):
            catalog_import_service.load_contact_persons(rows)

    def test_inactive_contact_is_turned_on(self) -> None:
        link = OrganizationContactFactory(
            organization=OrganizationFactory(name="МГУ"),
            contact__full_name="Иванов Иван",
            contact__is_active=False,
            position="Проректор",
        )
        rows = iter([(2, {"full_name": "Иванов Иван", "organization": "МГУ", "position": "Декан"})])

        created, updated = catalog_import_service.load_contact_persons(rows)

        link.refresh_from_db()
        link.contact.refresh_from_db()
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual((link.contact.is_active, link.position), (True, "Декан"))


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
        OrganizationFactory(name="МГУ")
        rows = iter(
            [
                (2, {"full_name": "Иванов Иван", "organization": "МГУ"}),
                (3, {"full_name": "Петров Пётр", "organization": "Неизвестный вуз"}),
            ]
        )

        with self.assertRaises(CatalogImportRowsError) as context:
            catalog_import_service.load_contact_persons(rows)

        [error] = context.exception.errors
        self.assertEqual((error.row_number, error.message), (3, "организация не найдена: Неизвестный вуз"))
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
        organization = OrganizationFactory(name="МГУ")
        OrganizationContactFactory(organization=organization, contact__full_name="Иванов Иван")
        rows = iter([(2, {"full_name": "ИВАНОВ ИВАН", "organization": "мгу", "email": "ivanov@example.com"})])

        created, updated = catalog_import_service.load_contact_persons(rows)

        self.assertEqual((created, updated), (0, 1))
        contact = ContactPerson.objects.get()
        self.assertEqual((contact.full_name, contact.email), ("ИВАНОВ ИВАН", "ivanov@example.com"))


class FileColumnsAreSourceOfTruthTestCase(TestCase):
    """Колонки нет — поле не меняется; ячейка пуста — значение стирается; пустой код не стирается."""

    def test_missing_is_active_column_keeps_inactive_vendor(self) -> None:
        Vendor.objects.create(name="Вендор", external_code="V-1", is_active=False)

        catalog_import_service.load_vendors(iter([(2, {"name": "Вендор", "external_code": "V-1"})]))

        # Проверяем, что вендор остался неактивным
        self.assertFalse(Vendor.objects.get().is_active)

    def test_missing_is_active_column_creates_active_record(self) -> None:
        catalog_import_service.load_directions(iter([(2, {"name": "Направление", "external_code": "D-1"})]))

        # Проверяем значение по умолчанию у новой записи
        self.assertTrue(Direction.objects.get().is_active)

    def test_present_is_active_column_updates_flag(self) -> None:
        Vendor.objects.create(name="Вендор", external_code="V-1", is_active=False)

        catalog_import_service.load_vendors(iter([(2, {"name": "Вендор", "external_code": "V-1", "is_active": ""})]))

        # Проверяем, что пустая ячейка — «активен»
        self.assertTrue(Vendor.objects.get().is_active)

    def test_empty_code_keeps_saved_vendor_code(self) -> None:
        Vendor.objects.create(name="Вендор", external_code="V-1")

        created, updated = catalog_import_service.load_vendors(iter([(2, {"name": "вендор", "external_code": ""})]))

        # Проверяем, что запись найдена по названию, а код сохранился
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(Vendor.objects.get().external_code, "V-1")

    def test_empty_code_keeps_saved_product_code(self) -> None:
        vendor = VendorFactory(name="Вендор")
        Product.objects.create(name="Продукт", external_code="P-1", vendor=vendor)

        catalog_import_service.load_products(
            iter([(2, {"name": "Продукт", "external_code": "", "vendor": "Вендор", "is_active": "нет"})])
        )

        # Проверяем, что код сохранился, а активность обновилась
        product = Product.objects.get()
        self.assertEqual((product.external_code, product.is_active), ("P-1", False))

    def test_filled_code_replaces_saved_code(self) -> None:
        Vendor.objects.create(name="Вендор", external_code="V-1")

        catalog_import_service.load_vendors(iter([(2, {"name": "Вендор", "external_code": "V-2"})]))

        # Проверяем, что найденная по названию запись получила новый код
        self.assertEqual(Vendor.objects.get().external_code, "V-2")

    def test_missing_program_active_column_keeps_flag(self) -> None:
        direction = DirectionFactory(name="DevOps")
        Program.objects.create(name="DevOps-инженер", direction=direction, is_active=False)

        catalog_import_service.load_programs(iter([(2, {"name": "DevOps-инженер", "direction": "DevOps"})]))

        # Проверяем, что программа осталась неактивной
        self.assertFalse(Program.objects.get().is_active)

    def test_missing_contact_columns_keep_values(self) -> None:
        organization = OrganizationFactory(name="МГУ")
        OrganizationContactFactory(
            organization=organization,
            position="Ректор",
            contact__full_name="Иванов Иван",
            contact__email="a@example.com",
            contact__phone="1",
        )

        catalog_import_service.load_contact_persons(
            iter([(2, {"full_name": "Иванов Иван", "organization": "МГУ", "phone": "2"})])
        )

        # Проверяем, что отсутствующие колонки не тронуты, а телефон обновлён
        link = OrganizationContact.objects.select_related("contact").get()
        self.assertEqual((link.position, link.contact.email, link.contact.phone), ("Ректор", "a@example.com", "2"))

    def test_empty_affiliation_cells_clear_values_but_person_data_is_kept(self) -> None:
        """Должность — данные связи с вузом файла, стирается; email человека может прийти из другой организации."""
        organization = OrganizationFactory(name="МГУ")
        OrganizationContactFactory(
            organization=organization, position="Ректор", contact__full_name="Иванов Иван", contact__email="a@example.com"
        )

        catalog_import_service.load_contact_persons(
            iter([(2, {"full_name": "Иванов Иван", "organization": "МГУ", "position": "", "email": ""})])
        )

        # Проверяем, что пустая ячейка стёрла должность, но не email человека
        link = OrganizationContact.objects.select_related("contact").get()
        self.assertEqual((link.position, link.contact.email), ("", "a@example.com"))


class ReadableValueErrorsTestCase(TestCase):
    """Ошибки приведения значений ячеек понятны пользователю."""

    def test_text_instead_of_decimal(self) -> None:
        with self.assertRaisesMessage(ValueError, "ожидалось число, получено север"):
            import_file_service.to_decimal("север")

    def test_text_instead_of_positive_int(self) -> None:
        with self.assertRaisesMessage(ValueError, "ожидалось число, получено много"):
            import_file_service.to_positive_int("много")

    def test_text_instead_of_year(self) -> None:
        with self.assertRaisesMessage(ValueError, "ожидалось число, получено двадцать седьмой"):
            import_file_service.to_year("двадцать седьмой")

    def test_fractional_year(self) -> None:
        with self.assertRaisesMessage(ValueError, "ожидался год целым числом, получено 2026.5"):
            import_file_service.to_year(2026.5)

    def test_year_from_float_cell(self) -> None:
        # Проверяем, что год из числовой ячейки xlsx читается без дробной части
        self.assertEqual(import_file_service.to_year(2027.0), 2027)

    def test_organization_row_error_message(self) -> None:
        row = {
            "id": "", "ror": "R-1", "name_en": "", "name": "Вуз", "short_name": "", "country_code": "", "type": "",
            "works_count": "", "cited_by_count": "", "city": "", "region": "", "lat": "север", "lon": "",
            "homepage_url": "",
        }

        with self.assertRaises(CatalogImportRowsError) as context:
            catalog_import_service.load_organizations(iter([(2, row)]))

        # Проверяем текст ошибки строки
        self.assertEqual(context.exception.errors[0].message, "ожидалось число, получено север")
        self.assertFalse(Organization.objects.exists())
