from datetime import date

from django.test import TestCase

from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.models import ContactPerson
from sova.catalog.services import contract_registry_import_service
from sova.catalog.tests.factories import DirectionFactory, ProductFactory, ProgramFactory, UniversityFactory, VendorFactory
from sova.interactions.models import Contract, InteractionProduct, License


class ImportContractRegistryTestCase(TestCase):
    """Импорт реестра создаёт headless Contract + продукты/лицензии, группируя строки по номеру договора."""

    def setUp(self) -> None:
        self.university = UniversityFactory(name="МГУ")
        self.vendor = VendorFactory(name="1С")
        self.product = ProductFactory(name="1С:Предприятие", vendor=self.vendor)

    def _row(self, **overrides) -> dict:
        row = {
            "university": "МГУ",
            "vendor": "1С",
            "product": "1С:Предприятие",
            "contract_number": "Д-1",
            "license_signed": "да",
            "license_valid_until_year": "2027",
            "draft_status": "В работе",
            "draft_manager_full_name": "Иванов Иван",
            "university_contact": "Петров Пётр",
            "draft_comment": "Первичный контакт",
        }
        row.update(overrides)
        return row

    def test_creates_headless_contract_with_product_and_license(self) -> None:
        rows = iter([(2, self._row())])

        created, updated = contract_registry_import_service.import_rows(rows)

        self.assertEqual((created, updated), (1, 0))
        contract = Contract.objects.get(contract_number="Д-1")
        self.assertIsNone(contract.interaction_id)
        self.assertEqual(contract.university_id, self.university.id)
        self.assertEqual(contract.draft_manager_full_name, "Иванов Иван")
        self.assertEqual(contract.draft_status, "В работе")

        item = InteractionProduct.objects.get(contract=contract, product=self.product)
        self.assertIsNone(item.interaction_id)
        license_ = License.objects.get(contract=contract, interaction_product=item)
        self.assertTrue(license_.is_signed)
        self.assertEqual(license_.valid_until_year, 2027)

    def test_signed_date_in_license_column_marks_license_signed(self) -> None:
        """Дата в колонке «лицензия подписана» — это и факт, и дата подписания."""
        rows = iter([(2, self._row(license_signed=date(2026, 3, 1), license_valid_until_year=2027.0))])

        contract_registry_import_service.import_rows(rows)

        license_ = License.objects.get(contract__contract_number="Д-1")
        self.assertTrue(license_.is_signed)
        self.assertEqual(license_.signed_at, date(2026, 3, 1))
        self.assertEqual(license_.valid_until_year, 2027)

    def test_groups_multiple_rows_with_same_contract_number_into_one_contract(self) -> None:
        other_product = ProductFactory(name="Docker", vendor=self.vendor)
        rows = iter(
            [
                (2, self._row()),
                (3, self._row(product="Docker")),
            ]
        )

        created, updated = contract_registry_import_service.import_rows(rows)

        self.assertEqual((created, updated), (1, 0))
        contract = Contract.objects.get(contract_number="Д-1")
        self.assertEqual(
            set(InteractionProduct.objects.filter(contract=contract).values_list("product_id", flat=True)),
            {self.product.id, other_product.id},
        )

    def test_second_import_updates_existing_headless_contract(self) -> None:
        contract_registry_import_service.import_rows(iter([(2, self._row())]))

        created, updated = contract_registry_import_service.import_rows(iter([(2, self._row(draft_status="Передано"))]))

        self.assertEqual((created, updated), (0, 1))
        contract = Contract.objects.get(contract_number="Д-1")
        self.assertEqual(contract.draft_status, "Передано")

    def test_contract_number_and_contacts_are_matched_in_other_case(self) -> None:
        contract_registry_import_service.import_rows(iter([(2, self._row(contract_number="Д-15/2026"))]))

        created, updated = contract_registry_import_service.import_rows(
            iter([(2, self._row(contract_number="д-15/2026", university="мгу", university_contact="ПЕТРОВ ПЁТР"))])
        )

        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(Contract.objects.get().contract_number, "Д-15/2026")
        self.assertEqual(ContactPerson.objects.count(), 1)

    def test_conflicting_values_within_one_group_raise(self) -> None:
        rows = iter([(2, self._row()), (3, self._row(product="1С:Предприятие", draft_status="Передано"))])

        with self.assertRaises(CatalogImportError):
            contract_registry_import_service.import_rows(rows)

    def test_error_in_any_row_rolls_back_whole_file(self) -> None:
        rows = iter(
            [
                (2, self._row()),
                (3, self._row(contract_number="Д-2", product="Неизвестный продукт")),
            ]
        )

        with self.assertRaises(CatalogImportError):
            contract_registry_import_service.import_rows(rows)

        self.assertFalse(Contract.objects.exists())
        self.assertFalse(License.objects.exists())
        self.assertFalse(ContactPerson.objects.exists())

    def test_collects_errors_from_all_rows(self) -> None:
        rows = iter(
            [
                (2, self._row(product="Неизвестный продукт")),
                (3, self._row(contract_number="Д-2")),
                (4, self._row(contract_number="", product="1С:Предприятие")),
            ]
        )

        with self.assertRaises(CatalogImportRowsError) as context:
            contract_registry_import_service.import_rows(rows)

        self.assertEqual(
            [(error.row_number, error.message) for error in context.exception.errors],
            [(2, "продукт не найден: Неизвестный продукт"), (4, "поле contract_number обязательно")],
        )
        self.assertFalse(Contract.objects.exists())

    def test_optional_program_resolves_direction_transitively(self) -> None:
        direction = DirectionFactory(name="DevOps")
        program = ProgramFactory(name="DevOps-инженер с нуля", direction=direction)
        rows = iter([(2, self._row(program="DevOps-инженер с нуля"))])

        contract_registry_import_service.import_rows(rows)

        contract = Contract.objects.get(contract_number="Д-1")
        item = InteractionProduct.objects.get(contract=contract, product=self.product)
        self.assertEqual(item.interaction_program.program_id, program.id)
        self.assertEqual(item.interaction_program.contract_id, contract.id)
        self.assertTrue(contract.interaction_directions.filter(direction=direction).exists())

    def test_conflicting_direction_and_program_raises(self) -> None:
        DirectionFactory(name="QA")
        ProgramFactory(name="DevOps-инженер с нуля", direction=DirectionFactory(name="DevOps"))
        rows = iter([(2, self._row(program="DevOps-инженер с нуля", direction="QA"))])

        with self.assertRaises(CatalogImportError):
            contract_registry_import_service.import_rows(rows)

    def test_unknown_product_raises(self) -> None:
        rows = iter([(2, self._row(product="Неизвестный продукт"))])

        with self.assertRaises(CatalogImportError):
            contract_registry_import_service.import_rows(rows)

    def test_creates_contact_persons_from_university_contact_column(self) -> None:
        rows = iter([(2, self._row(university_contact="Петров Пётр; Сидорова Анна"))])

        contract_registry_import_service.import_rows(rows)

        self.assertTrue(ContactPerson.objects.filter(university=self.university, full_name="Петров Пётр").exists())
        self.assertTrue(ContactPerson.objects.filter(university=self.university, full_name="Сидорова Анна").exists())
