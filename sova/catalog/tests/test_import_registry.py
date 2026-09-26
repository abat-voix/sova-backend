from datetime import date

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import SystemRole, UserRole

from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.models import ContactPerson
from sova.catalog.services import contract_registry_import_service
from sova.catalog.tests.factories import DirectionFactory, ProductFactory, ProgramFactory, UniversityFactory, VendorFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Contract, InteractionProduct, License, Responsible
from sova.interactions.services.contract_attachment import contract_attachment_service


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
            "manager_full_name": "Иванов Иван",
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

    def test_attached_contract_rows_are_skipped_with_warning(self) -> None:
        """Реестр — только для создания взаимодействий: привязанный договор не меняется и не дублируется."""
        contract_registry_import_service.import_rows(iter([(2, self._row())]))
        contract = Contract.objects.get(contract_number="Д-1")
        contract_attachment_service.attach_to_new_interaction(contract=contract, author=None)
        warnings: list = []

        created, updated = contract_registry_import_service.import_rows(
            iter([(2, self._row(contract_number="д-1", draft_status="Передано", product="Неизвестный продукт"))]),
            warnings=warnings,
        )

        # Проверяем: строки пропущены без ошибок, договор один и не изменён, есть предупреждение
        self.assertEqual((created, updated), (0, 0))
        self.assertEqual(Contract.objects.filter(contract_number__iexact="Д-1").count(), 1)
        contract.refresh_from_db()
        self.assertEqual(contract.draft_status, "В работе")
        self.assertEqual(
            [str(warning) for warning in warnings],
            ["Строка 2: договор д-1 уже привязан к взаимодействию, его строки не загружены"],
        )

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
            draft_status="Черновик",
            draft_comment="Старый комментарий",
        )

    def _row(self, product: str, **drafts) -> dict:
        return {"university": "МГУ", "vendor": "1С", "product": product, "contract_number": "Д-1", **drafts}

    def _drafts(self) -> tuple[str, str]:
        contract = Contract.objects.get(contract_number="Д-1")
        return contract.draft_status, contract.draft_comment

    def test_value_is_taken_from_any_filled_row(self) -> None:
        empty = {"draft_status": "", "draft_comment": ""}
        rows = [
            (2, self._row("IDE", **{**empty, "draft_status": "Передан"})),
            (3, self._row("СУБД", **empty)),
            (4, self._row("ML", **{**empty, "draft_comment": "Продление"})),
        ]

        created, updated = contract_registry_import_service.import_rows(iter(rows))

        # Проверяем, что значения собраны из разных строк договора
        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(self._drafts(), ("Передан", "Продление"))

    def test_column_empty_in_all_rows_clears_value(self) -> None:
        empty = {"draft_status": "", "draft_comment": ""}
        rows = [
            (2, self._row("IDE", **{**empty, "draft_status": "Передан"})),
            (3, self._row("СУБД", **empty)),
        ]

        contract_registry_import_service.import_rows(iter(rows))

        # Проверяем, что пустой во всех строках комментарий стёрт
        self.assertEqual(self._drafts(), ("Передан", ""))

    def test_missing_columns_keep_values(self) -> None:
        contract_registry_import_service.import_rows(iter([(2, self._row("IDE"))]))

        # Проверяем, что черновые поля не тронуты
        self.assertEqual(self._drafts(), ("Черновик", "Старый комментарий"))

    def test_different_values_in_one_contract_raise(self) -> None:
        rows = [
            (2, self._row("IDE", draft_status="Передан")),
            (3, self._row("СУБД", draft_status="Подписан")),
        ]

        with self.assertRaises(CatalogImportRowsError) as context:
            contract_registry_import_service.import_rows(iter(rows))

        # Проверяем, что ошибка во второй строке и только по статусу
        [error] = context.exception.errors
        self.assertEqual(
            (error.row_number, error.message),
            (3, "расходятся значения внутри группы договора Д-1: draft_status"),
        )
        self.assertEqual(self._drafts(), ("Черновик", "Старый комментарий"))

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
    """«ФИО Менеджера» назначает КАМов договора; файл — источник правды, ненайденное ФИО — предупреждение."""

    def setUp(self) -> None:
        self.university = UniversityFactory(name="МГУ")
        vendor = VendorFactory(name="1С")
        ProductFactory(name="IDE", vendor=vendor)
        ProductFactory(name="СУБД", vendor=vendor)
        self.ivanov = self._user("Иван", "Иванов")
        self.petrov = self._user("Пётр", "Петров")
        self.importer = UserFactory()

    @staticmethod
    def _user(first_name: str, last_name: str, role: str | None = SystemRole.KAM):
        user = UserFactory(first_name=first_name, last_name=last_name)
        if role is not None:
            UserRole.objects.create(user=user, role=role)
        return user

    def _row(self, product: str = "IDE", **extra) -> dict:
        return {"university": "МГУ", "vendor": "1С", "product": product, "contract_number": "Д-1", **extra}

    def _import(self, *rows: dict) -> list:
        warnings: list = []
        contract_registry_import_service.import_rows(
            iter([(number, row) for number, row in enumerate(rows, start=2)]), warnings=warnings, user=self.importer
        )
        return warnings

    def _current(self) -> set[int]:
        return set(
            Responsible.objects.filter(contract__contract_number="Д-1", unassigned_at__isnull=True).values_list(
                "manager_id", flat=True
            )
        )

    def test_names_from_all_rows_become_contract_responsibles(self) -> None:
        warnings = self._import(
            self._row(manager_full_name="Иванов Иван"), self._row("СУБД", manager_full_name="Петров Пётр")
        )

        # Проверяем: оба КАМа назначены договору от имени загрузившего, без взаимодействия, без предупреждений
        self.assertEqual(self._current(), {self.ivanov.pk, self.petrov.pk})
        self.assertEqual(
            set(Responsible.objects.values_list("assigned_by_id", "interaction_id")), {(self.importer.pk, None)}
        )
        self.assertEqual(warnings, [])

    def test_same_kam_in_different_word_order_is_assigned_once(self) -> None:
        self._import(self._row(manager_full_name="Иванов Иван"), self._row("СУБД", manager_full_name="Иван Иванов"))

        # Проверяем одно назначение
        self.assertEqual(Responsible.objects.count(), 1)

    def test_only_kam_role_is_resolved(self) -> None:
        self._user("Сидор", "Сидоров", role=SystemRole.HEAD)
        self._user("Семён", "Семёнов", role=None)

        warnings = self._import(
            self._row(manager_full_name="Сидоров Сидор"), self._row("СУБД", manager_full_name="Семёнов Семён")
        )

        # Проверяем: руководитель и пользователь без роли не назначены, по каждому — предупреждение на его строке
        self.assertEqual(self._current(), set())
        self.assertEqual(
            [(warning.row_number, warning.message) for warning in warnings],
            [
                (2, "менеджер Сидоров Сидор договора Д-1 не назначен: нет КАМа с таким ФИО"),
                (3, "менеджер Семёнов Семён договора Д-1 не назначен: нет КАМа с таким ФИО"),
            ],
        )

    def test_ambiguous_name_gives_warning(self) -> None:
        self._user("Иван", "Иванов")

        warnings = self._import(self._row(manager_full_name="Иванов Иван"))

        # Проверяем: назначения нет, причина — однофамильцы
        self.assertEqual(self._current(), set())
        self.assertEqual(warnings[0].message, "менеджер Иванов Иван договора Д-1 не назначен: несколько КАМов с таким ФИО")

    def test_reimport_syncs_with_file(self) -> None:
        self._import(self._row(manager_full_name="Иванов Иван"), self._row("СУБД", manager_full_name="Петров Пётр"))

        self._import(self._row(manager_full_name="Иванов Иван"), self._row("СУБД", manager_full_name="Иванов Иван"))

        # Проверяем: Иванов остался, Петров снят и остался в истории
        self.assertEqual(self._current(), {self.ivanov.pk})
        self.assertIsNotNone(Responsible.objects.get(manager=self.petrov).unassigned_at)

    def test_same_file_twice_keeps_history(self) -> None:
        self._import(self._row(manager_full_name="Иванов Иван"))
        self._import(self._row(manager_full_name="Иванов Иван"))

        # Проверяем, что повторная загрузка не закрывает и не пересоздаёт назначение
        self.assertEqual(Responsible.objects.count(), 1)

    def test_unrecognized_name_on_reimport_unassigns(self) -> None:
        self._import(self._row(manager_full_name="Иванов Иван"))

        warnings = self._import(self._row(manager_full_name="Иванов И."))

        # Проверяем: файл — источник правды, КАМ снят, есть предупреждение
        self.assertEqual(self._current(), set())
        self.assertEqual(len(warnings), 1)

    def test_missing_column_keeps_responsibles(self) -> None:
        self._import(self._row(manager_full_name="Иванов Иван"))

        self._import(self._row())

        # Проверяем, что без колонки ответственные не тронуты
        self.assertEqual(self._current(), {self.ivanov.pk})

    def test_empty_column_unassigns_all(self) -> None:
        self._import(self._row(manager_full_name="Иванов Иван"))

        warnings = self._import(self._row(manager_full_name=""))

        # Проверяем: колонка есть, но пуста — ответственных у договора нет, предупреждений нет
        self.assertEqual(self._current(), set())
        self.assertEqual(warnings, [])

    def test_file_with_errors_assigns_nothing(self) -> None:
        warnings: list = []
        rows = [
            (2, self._row(manager_full_name="Иванов Иван")),
            (3, {**self._row(product="Неизвестный продукт"), "contract_number": "Д-2"}),
        ]

        with self.assertRaises(CatalogImportRowsError):
            contract_registry_import_service.import_rows(iter(rows), warnings=warnings, user=self.importer)

        # Проверяем: импорт отменён, назначений и предупреждений нет
        self.assertFalse(Responsible.objects.exists())
        self.assertEqual(warnings, [])

    def test_existing_headless_contract_is_locked(self) -> None:
        """Импорт блокирует найденный договор: параллельная привязка дождётся конца импорта и увидит его КАМов."""
        self._import(self._row(manager_full_name="Иванов Иван"))

        with CaptureQueriesContext(connection) as context:
            self._import(self._row(manager_full_name="Петров Пётр"))

        # Проверяем, что поиск договора в реестре идёт с FOR UPDATE
        lookups = [
            query["sql"]
            for query in context.captured_queries
            if 'FROM "interactions_contract"' in query["sql"]
            and "UPPER" in query["sql"]
            and '"interactions_contract"."interaction_id" IS NULL' in query["sql"]
        ]
        self.assertTrue(lookups)
        self.assertTrue(all("FOR UPDATE" in sql for sql in lookups))
