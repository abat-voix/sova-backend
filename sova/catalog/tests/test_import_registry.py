from datetime import date

from django.test import TestCase

from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.models import ContactPerson
from sova.catalog.services import contract_registry_import_service
from sova.catalog.tests.factories import DirectionFactory, ProductFactory, ProgramFactory, UniversityFactory, VendorFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Contract, InteractionProduct, License, Responsible


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


class ContractRegistryDraftFieldsTestCase(TestCase):
    """Черновые поля договора собираются по всем его строкам файла."""

    def setUp(self) -> None:
        self.university = UniversityFactory(name="МГУ")
        vendor = VendorFactory(name="1С")
        ProductFactory(name="IDE", vendor=vendor)
        ProductFactory(name="СУБД", vendor=vendor)
        ProductFactory(name="ML", vendor=vendor)
        Contract.objects.create(
            contract_number="Д-1",
            university=self.university,
            draft_manager_full_name="Иванов",
            draft_status="Черновик",
            draft_comment="Старый комментарий",
        )

    def _row(self, product: str, **drafts) -> dict:
        return {"university": "МГУ", "vendor": "1С", "product": product, "contract_number": "Д-1", **drafts}

    def _drafts(self) -> tuple[str, str, str]:
        contract = Contract.objects.get(contract_number="Д-1")
        return contract.draft_manager_full_name, contract.draft_status, contract.draft_comment

    def test_value_is_taken_from_any_filled_row(self) -> None:
        empty = {"draft_manager_full_name": "", "draft_status": "", "draft_comment": ""}
        rows = [
            (2, self._row("IDE", **{**empty, "draft_manager_full_name": "Петров", "draft_status": "Передан"})),
            (3, self._row("СУБД", **empty)),
            (4, self._row("ML", **{**empty, "draft_comment": "Продление"})),
        ]

        created, updated = contract_registry_import_service.import_rows(iter(rows))

        # Проверяем, что значения собраны из разных строк договора
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(self._drafts(), ("Петров", "Передан", "Продление"))

    def test_column_empty_in_all_rows_clears_value(self) -> None:
        empty = {"draft_manager_full_name": "", "draft_status": "", "draft_comment": ""}
        rows = [
            (2, self._row("IDE", **{**empty, "draft_manager_full_name": "Петров"})),
            (3, self._row("СУБД", **empty)),
        ]

        contract_registry_import_service.import_rows(iter(rows))

        # Проверяем, что пустые во всех строках статус и комментарий стёрты
        self.assertEqual(self._drafts(), ("Петров", "", ""))

    def test_missing_columns_keep_values(self) -> None:
        contract_registry_import_service.import_rows(iter([(2, self._row("IDE"))]))

        # Проверяем, что черновые поля не тронуты
        self.assertEqual(self._drafts(), ("Иванов", "Черновик", "Старый комментарий"))

    def test_different_values_in_one_contract_raise(self) -> None:
        rows = [
            (2, self._row("IDE", draft_manager_full_name="Петров", draft_status="Передан")),
            (3, self._row("СУБД", draft_manager_full_name="Сидоров", draft_status="Передан")),
        ]

        with self.assertRaises(CatalogImportRowsError) as context:
            contract_registry_import_service.import_rows(iter(rows))

        # Проверяем, что ошибка во второй строке и только по менеджеру
        [error] = context.exception.errors
        self.assertEqual(
            (error.row_number, error.message),
            (3, "расходятся значения внутри группы договора Д-1: draft_manager_full_name"),
        )
        self.assertEqual(self._drafts(), ("Иванов", "Черновик", "Старый комментарий"))

    def test_contracts_are_grouped_by_university_and_number_case(self) -> None:
        UniversityFactory(name="МФТИ", external_code="R-2")
        rows = [
            (2, self._row("IDE", draft_status="Подписан")),
            (3, {**self._row("СУБД", draft_status=""), "contract_number": "д-1", "university": "мгу"}),
            (4, {**self._row("IDE", draft_status=""), "university": "R-2"}),
        ]

        created, updated = contract_registry_import_service.import_rows(iter(rows))

        # Проверяем: МГУ/Д-1 — один договор со статусом, МФТИ/Д-1 — новый договор без статуса
        self.assertEqual((created, updated), (1, 1))
        self.assertEqual(Contract.objects.get(university=self.university).draft_status, "Подписан")
        self.assertEqual(Contract.objects.get(university__name="МФТИ").draft_status, "")

    def test_new_contract_takes_value_from_any_row(self) -> None:
        rows = [
            (2, {**self._row("IDE", draft_status=""), "contract_number": "Д-2"}),
            (3, {**self._row("СУБД", draft_status="Черновик"), "contract_number": "Д-2"}),
        ]

        contract_registry_import_service.import_rows(iter(rows))

        # Проверяем статус нового договора
        self.assertEqual(Contract.objects.get(contract_number="Д-2").draft_status, "Черновик")


class ContractRegistryManagersTestCase(TestCase):
    """«ФИО Менеджера» не назначается: ненайденный пользователь — предупреждение импорта."""

    def setUp(self) -> None:
        self.university = UniversityFactory(name="МГУ")
        vendor = VendorFactory(name="1С")
        ProductFactory(name="IDE", vendor=vendor)
        ProductFactory(name="СУБД", vendor=vendor)
        self.manager = UserFactory(first_name="Максим", last_name="Менеджеров")

    def _row(self, product: str = "IDE", **extra) -> dict:
        return {"university": "МГУ", "vendor": "1С", "product": product, "contract_number": "Д-1", **extra}

    def _import(self, *rows: dict) -> list:
        warnings: list = []
        contract_registry_import_service.import_rows(
            iter([(number, row) for number, row in enumerate(rows, start=2)]), warnings=warnings
        )
        return warnings

    def test_found_manager_is_not_assigned_and_gives_no_warning(self) -> None:
        warnings = self._import(self._row(draft_manager_full_name="Менеджеров Максим"))

        # Проверяем: ФИО сохранено, назначений нет, предупреждений нет
        self.assertEqual(Contract.objects.get().draft_manager_full_name, "Менеджеров Максим")
        self.assertFalse(Responsible.objects.exists())
        self.assertEqual(warnings, [])

    def test_unknown_manager_gives_warning_on_row_with_name(self) -> None:
        warnings = self._import(
            self._row(draft_manager_full_name=""), self._row("СУБД", draft_manager_full_name="Петров Пётр")
        )

        # Проверяем предупреждение на строке, где указано ФИО
        [warning] = warnings
        self.assertEqual(
            (warning.row_number, warning.message),
            (3, "менеджер Петров Пётр договора Д-1 не будет предложен ответственным: нет пользователя с таким ФИО"),
        )

    def test_ambiguous_manager_gives_warning(self) -> None:
        UserFactory(first_name="Максим", last_name="Менеджеров")

        warnings = self._import(self._row(draft_manager_full_name="Менеджеров Максим"))

        # Проверяем причину — однофамильцы
        self.assertIn("несколько пользователей с таким ФИО", warnings[0].message)

    def test_empty_or_missing_manager_gives_no_warning(self) -> None:
        # Проверяем пустую ячейку и отсутствие колонки
        self.assertEqual(self._import(self._row(draft_manager_full_name="")), [])
        self.assertEqual(self._import(self._row()), [])

    def test_file_with_errors_returns_no_warnings(self) -> None:
        warnings: list = []
        rows = [
            (2, self._row(draft_manager_full_name="Петров Пётр")),
            (3, {**self._row(product="Неизвестный продукт"), "contract_number": "Д-2"}),
        ]

        with self.assertRaises(CatalogImportRowsError):
            contract_registry_import_service.import_rows(iter(rows), warnings=warnings)

        # Проверяем: импорт отменён, предупреждений нет — есть только ошибки
        self.assertEqual(warnings, [])
