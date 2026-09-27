from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase
from openpyxl import Workbook

from sova.catalog.enum import CatalogType
from sova.catalog.exceptions import CatalogImportRowsError
from sova.catalog.models import CatalogImportMapping, ContactPerson, Product, Vendor, VendorContact
from sova.catalog.services import catalog_import_service
from sova.catalog.tests.factories import ProductFactory, UniversityContactFactory, VendorContactFactory, VendorFactory

# Строки docs/Хакатон/Вендоры.xlsx: Компания · Продукт · ФИО · Телефон · Почта · Способ связи.
_HEADERS = ("Компания", "Продукт", "ФИО", "Телефон", "Почта", "Способ связи")
_FILE_ROWS = (
    ("ООО «Базис»", "«Базис Dynamix»", "Иванов Иван Иванович", "+7 (900) 111-22-33", "ivanov.ii@example.ru", "Почта, Чат в ТГ"),
    ("ООО «ТДата»", "«RT.DataLake», «RT.Warehouse»", "Смирнова Анна Петровна", "+7 (911) 222-33-44", "smirnova.ap@example.ru", "Чат в ТГ"),
    ("ПАО «Ростелеком»", "«RT.DataVision»", "Кузнецов Дмитрий Сергеевич", "+7 (922) 333-44-55", "kuznetsov.ds@example.ru", "Чат в ТГ"),
    ("ООО «РТК ИТ Плюс»", "«AKOLA»", "Попова Мария Владимировна", "+7 (933) 444-55-66", "popova.mv@example.ru", "Чат в ТГ"),
    ("ООО «РТК ИТ Плюс»", "«Яга»", "Соколов Алексей Андреевич", "+7 (944) 555-66-77", "sokolov.aa@example.ru", "Чат в ТГ"),
    ("ООО «РТК ИТ»", "«Web3Gate»", "Лебедева Елена Дмитриевна", "+7 (955) 666-77-88", "lebedeva.ed@example.ru", "Чат в ТГ"),
    ("ООО «РТК ИТ»", "«Аврора SDK»", "Козлов Максим Игоревич", "+7 (966) 777-88-99", "kozlov.mi@example.ru", "Чат в ТГ"),
    ("ООО «РТК ИТ»", "«Нейрошлюз»", "Новикова Ольга Александровна", "+7 (977) 888-99-00", "novikova.oa@example.ru", "Почта"),
)
_MAPPING = {
    "Компания": "name",
    "Продукт": "products",
    "ФИО": "contact_full_name",
    "Телефон": "contact_phone",
    "Почта": "contact_email",
    "Способ связи": "contact_channels",
}


def _row(name: str, products: str = "", full_name: str = "", **contact) -> dict:
    """Строка с каноническими ключами нового формата."""
    return {
        "name": name,
        "products": products,
        "contact_full_name": full_name,
        **{f"contact_{key}": value for key, value in contact.items()},
    }


class VendorFileImportTestCase(TestCase):
    """Файл Вендоры.xlsx через маппинг колонок: вендоры, продукты и контакты."""

    def setUp(self) -> None:
        for source_column, target_field in _MAPPING.items():
            CatalogImportMapping.objects.create(
                catalog_type=CatalogType.VENDOR, source_column=source_column, target_field=target_field
            )

    def _import(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "Вендоры.xlsx"
            workbook = Workbook()
            for row in (_HEADERS, *_FILE_ROWS):
                workbook.active.append(row)
            workbook.save(source)
            return catalog_import_service.import_file(CatalogType.VENDOR, source)

    def test_imports_vendors_products_and_contacts(self) -> None:
        result = self._import()

        self.assertEqual((result.created, result.updated), (5, 0))
        self.assertEqual(Product.objects.count(), 9)
        self.assertEqual(ContactPerson.objects.count(), 8)
        self.assertEqual(VendorContact.objects.count(), 8)
        smirnova = VendorContact.objects.get(contact__full_name="Смирнова Анна Петровна")
        self.assertEqual(smirnova.vendor.name, "ООО «ТДата»")
        self.assertEqual(sorted(smirnova.products.values_list("name", flat=True)), ["RT.DataLake", "RT.Warehouse"])
        ivanov = VendorContact.objects.get(contact__full_name="Иванов Иван Иванович")
        self.assertEqual(ivanov.preferred_channels, ["email", "telegram"])
        self.assertEqual(ivanov.contact.email, "ivanov.ii@example.ru")
        self.assertEqual(list(ivanov.products.values_list("name", flat=True)), ["Базис Dynamix"])

    def test_repeated_import_is_idempotent(self) -> None:
        self._import()

        result = self._import()

        self.assertEqual((result.created, result.updated), (0, 5))
        self.assertEqual((Vendor.objects.count(), Product.objects.count()), (5, 9))
        self.assertEqual((ContactPerson.objects.count(), VendorContact.objects.count()), (8, 8))
        self.assertEqual(result.warnings, [])


class VendorRowsImportTestCase(TestCase):
    """Правила разбора строк: кавычки, списки продуктов, сопоставление вендоров, продуктов и людей."""

    def _load(self, *rows: dict, warnings: list | None = None):
        return catalog_import_service.load_vendors(
            iter((number, row) for number, row in enumerate(rows, start=2)), warnings=warnings
        )

    def test_quotes_are_normalized_and_matched(self) -> None:
        vendor = VendorFactory(name="ООО «Базис»")

        self._load(_row('ООО "Базис"', products='"Базис Dynamix"; «Система «Яга»», «Яга, Pro»'))

        self.assertEqual(Vendor.objects.get().pk, vendor.pk)
        self.assertEqual(
            sorted(vendor.products.values_list("name", flat=True)), ["Базис Dynamix", "Система «Яга»", "Яга, Pro"]
        )

    def test_vendor_without_quotes_matches_quoted(self) -> None:
        vendor = VendorFactory(name="ООО «Базис»")

        created, updated = self._load(_row("ООО Базис"))

        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(Vendor.objects.get().pk, vendor.pk)

    def test_unbalanced_quotes_are_row_error(self) -> None:
        with self.assertRaises(CatalogImportRowsError) as context:
            self._load(_row("ООО «Базис", products="Базис"))

        self.assertIn("непарные кавычки", context.exception.errors[0].message)
        self.assertFalse(Vendor.objects.exists())

    def test_product_without_vendor_gets_vendor(self) -> None:
        product = Product.objects.create(name="Акола")

        self._load(_row("ООО «РТК ИТ Плюс»", products="«Акола»"))

        product.refresh_from_db()
        self.assertEqual(product.vendor.name, "ООО «РТК ИТ Плюс»")
        self.assertEqual(Product.objects.count(), 1)

    def test_product_of_other_vendor_is_created_with_warning(self) -> None:
        ProductFactory(name="Яга", vendor=VendorFactory(name="ПАО «Ростелеком»"))
        warnings: list = []

        self._load(_row("ООО «РТК ИТ Плюс»", products="«Яга»"), warnings=warnings)

        self.assertEqual(Product.objects.filter(name="Яга").count(), 2)
        self.assertEqual(len(warnings), 1)
        self.assertIn("ПАО «Ростелеком»", warnings[0].message)

    def test_contact_products_are_union_of_rows(self) -> None:
        self._load(
            _row("ООО «РТК ИТ»", products="Web3Gate", full_name="Козлов Максим"),
            _row("ООО «РТК ИТ»", products="Аврора SDK", full_name="Козлов Максим"),
        )

        link = VendorContact.objects.get()
        self.assertEqual(sorted(link.products.values_list("name", flat=True)), ["Web3Gate", "Аврора SDK"])

    def test_person_found_by_email_in_other_organization(self) -> None:
        university_link = UniversityContactFactory(contact__full_name="Иванов И. И.", contact__email="ivanov@example.ru")

        self._load(_row("ООО «Базис»", full_name="Иванов Иван Иванович", email="IVANOV@example.ru"))

        self.assertEqual(ContactPerson.objects.count(), 1)
        self.assertEqual(VendorContact.objects.get().contact_id, university_link.contact_id)
        university_link.contact.refresh_from_db()
        self.assertEqual(university_link.contact.full_name, "Иванов И. И.")

    def test_namesake_of_other_organization_is_new_person_with_warning(self) -> None:
        UniversityContactFactory(contact__full_name="Иванов Иван")
        warnings: list = []

        self._load(_row("ООО «Базис»", full_name="Иванов Иван"), warnings=warnings)

        self.assertEqual(ContactPerson.objects.count(), 2)
        self.assertEqual(len(warnings), 1)
        self.assertIn("похожие", warnings[0].message)

    def test_found_person_phone_is_updated(self) -> None:
        link = VendorContactFactory(vendor=VendorFactory(name="ООО «Базис»"), contact__full_name="Иванов Иван", contact__phone="1")

        self._load(_row("ООО «Базис»", full_name="Иванов Иван", phone="+7 900 000-00-00"))

        link.contact.refresh_from_db()
        self.assertEqual(link.contact.phone, "+7 900 000-00-00")

    def test_unknown_channel_is_row_error(self) -> None:
        with self.assertRaises(CatalogImportRowsError) as context:
            self._load(_row("ООО «Базис»", full_name="Иванов Иван", channels="Голубиная почта"))

        self.assertIn("неизвестный способ связи", context.exception.errors[0].message)

    def test_contact_data_without_full_name_is_row_error(self) -> None:
        with self.assertRaises(CatalogImportRowsError):
            self._load(_row("ООО «Базис»", email="ivanov@example.ru"))

    def test_invalid_telegram_is_row_error(self) -> None:
        with self.assertRaises(CatalogImportRowsError):
            self._load(_row("ООО «Базис»", full_name="Иванов Иван", telegram="ab"))

    def test_reference_file_format_still_works(self) -> None:
        created, updated = self._load({"name": "ПАО «Ростелеком»", "external_code": "rt", "is_active": "да"})

        self.assertEqual((created, updated), (1, 0))
        self.assertEqual(Vendor.objects.get().external_code, "rt")

    def test_inactive_person_is_turned_on(self) -> None:
        link = VendorContactFactory(
            vendor=VendorFactory(name="ООО «Базис»"),
            contact__full_name="Иванов Иван",
            contact__is_active=False,
            position="Консультант",
        )

        self._load(_row("ООО «Базис»", products="Базис Dynamix", full_name="Иванов Иван"))

        link.refresh_from_db()
        link.contact.refresh_from_db()
        self.assertTrue(link.contact.is_active)
        self.assertEqual(VendorContact.objects.filter(contact=link.contact).count(), 1)
        # Колонки должности в файле нет — прежняя должность сохраняется
        self.assertEqual(link.position, "Консультант")
        self.assertEqual(list(link.products.values_list("name", flat=True)), ["Базис Dynamix"])

    def test_inactive_person_found_by_email_gets_new_affiliation_and_is_turned_on(self) -> None:
        other = UniversityContactFactory(contact__email="ivanov@example.ru", contact__is_active=False)

        self._load(_row("ООО «Базис»", full_name="Иванов Иван", email="ivanov@example.ru"))

        self.assertTrue(ContactPerson.objects.get(pk=other.contact_id).is_active)
        self.assertTrue(VendorContact.objects.filter(contact_id=other.contact_id).exists())
