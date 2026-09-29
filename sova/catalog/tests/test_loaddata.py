from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from openpyxl import Workbook

from sova.catalog.models import Direction, Product, Program, Organization, Vendor
from sova.catalog.tests.factories import DirectionFactory, ProgramFactory, VendorFactory


class LoadOrganizationsCommandTestCase(TestCase):
    """Тесты загрузки справочника вузов из XLSX."""

    headers = (
        "id",
        "ror",
        "name_en",
        "name",
        "short_name",
        "country_code",
        "type",
        "works_count",
        "cited_by_count",
        "city",
        "region",
        "lat",
        "lon",
        "homepage_url",
    )

    def test_loads_and_updates_short_name(self) -> None:
        """Команда сохраняет краткое название при создании и обновлении вуза."""
        with TemporaryDirectory() as directory:
            source = Path(directory) / "organizations.xlsx"
            self._save_workbook(source, short_name="МГУ")

            call_command("loaddata", str(source), stdout=StringIO())

            organization = Organization.objects.get(external_code="https://ror.org/test")
            self.assertEqual(organization.short_name, "МГУ")

            self._save_workbook(source, short_name="МГУ имени М. В. Ломоносова")
            call_command("loaddata", str(source), stdout=StringIO())

            organization.refresh_from_db()
            self.assertEqual(
                organization.short_name,
                "МГУ имени М. В. Ломоносова",
            )

    def _save_workbook(self, path: Path, short_name: str) -> None:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(self.headers)
        worksheet.append(
            (
                "test-id",
                "https://ror.org/test",
                "Lomonosov Moscow State Organization",
                "Московский государственный университет",
                short_name,
                "ru",
                "education",
                100,
                200,
                "Москва",
                "Москва",
                "55.703934",
                "37.528669",
                "https://msu.ru",
            )
        )
        workbook.save(path)
        workbook.close()


def _write_workbook(path: Path, headers: tuple, *rows: tuple) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
    workbook.close()


class LoadVendorsCommandTestCase(TestCase):
    """Тесты загрузки справочника вендоров из XLSX."""

    headers = ("name", "external_code", "is_active")

    def test_loads_and_updates_is_active(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "vendors.xlsx"
            _write_workbook(source, self.headers, ("Вендор", "vendor-1", "да"))

            call_command("loaddata", str(source), stdout=StringIO())

            vendor = Vendor.objects.get(external_code="vendor-1")
            self.assertTrue(vendor.is_active)

            _write_workbook(source, self.headers, ("Вендор", "vendor-1", "нет"))
            call_command("loaddata", str(source), stdout=StringIO())

            vendor.refresh_from_db()
            self.assertFalse(vendor.is_active)
            self.assertEqual(Vendor.objects.count(), 1)

    def test_loads_reference_headers_with_vendor_contacts(self) -> None:
        """Штатный справочник вендоров использует понятные русские заголовки."""
        with TemporaryDirectory() as directory:
            source = Path(directory) / "vendors.xlsx"
            _write_workbook(
                source,
                ("Компания", "Продукт", "ФИО", "Телефон", "Почта", "Способ связи"),
                ("ООО «Базис»", "«Базис Dynamix»", "Иванов Иван", "+7 900 111-22-33", "ivanov@example.ru", "Почта"),
            )

            call_command("loaddata", str(source), stdout=StringIO())

            vendor = Vendor.objects.get(name="ООО «Базис»")
            self.assertTrue(vendor.products.filter(name="Базис Dynamix").exists())
            self.assertTrue(vendor.contact_links.filter(contact__full_name="Иванов Иван").exists())


class LoadDirectionsCommandTestCase(TestCase):
    """Тесты загрузки справочника направлений из XLSX."""

    def test_loads_by_name_without_external_code(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "directions.xlsx"
            _write_workbook(source, ("name", "external_code", "is_active"), ("DevOps", None, None))

            call_command("loaddata", str(source), stdout=StringIO())

            direction = Direction.objects.get(name="DevOps")
            self.assertTrue(direction.is_active)
            self.assertIsNone(direction.external_code)


class LoadProductsCommandTestCase(TestCase):
    """Тесты загрузки справочника продуктов из XLSX."""

    headers = ("name", "external_code", "vendor", "is_active")

    def test_resolves_vendor_and_upserts_by_external_code(self) -> None:
        vendor = VendorFactory(name="1С", external_code="vendor-1c")
        with TemporaryDirectory() as directory:
            source = Path(directory) / "products.xlsx"
            _write_workbook(source, self.headers, ("1С:Предприятие", "product-1", "vendor-1c", None))

            call_command("loaddata", str(source), stdout=StringIO())

            product = Product.objects.get(external_code="product-1")
            self.assertEqual(product.vendor_id, vendor.id)

    def test_unknown_vendor_raises(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "products.xlsx"
            _write_workbook(source, self.headers, ("Продукт", "product-1", "неизвестный вендор", None))

            with self.assertRaises(CommandError):
                call_command("loaddata", str(source), stdout=StringIO())

    def test_resolves_programs_and_links_via_m2m(self) -> None:
        program_one = ProgramFactory(name="DevOps-инженер с нуля")
        program_two = ProgramFactory(name="Инженер-тестировщик")
        headers = (*self.headers, "programs")
        with TemporaryDirectory() as directory:
            source = Path(directory) / "products.xlsx"
            _write_workbook(
                source,
                headers,
                ("Docker", "product-docker", None, None, "DevOps-инженер с нуля; Инженер-тестировщик"),
            )

            call_command("loaddata", str(source), stdout=StringIO())

            product = Product.objects.get(external_code="product-docker")
            self.assertCountEqual(product.programs.all(), [program_one, program_two])

    def test_omitted_programs_column_does_not_touch_existing_links(self) -> None:
        program = ProgramFactory(name="DevOps-инженер с нуля")
        product = Product.objects.create(name="Docker", external_code="product-docker")
        product.programs.set([program])
        with TemporaryDirectory() as directory:
            source = Path(directory) / "products.xlsx"
            _write_workbook(source, self.headers, ("Docker", "product-docker", None, None))

            call_command("loaddata", str(source), stdout=StringIO())

            self.assertCountEqual(product.programs.all(), [program])

    def test_unknown_program_raises(self) -> None:
        headers = (*self.headers, "programs")
        with TemporaryDirectory() as directory:
            source = Path(directory) / "products.xlsx"
            _write_workbook(source, headers, ("Docker", "product-docker", None, None, "неизвестная программа"))

            with self.assertRaises(CommandError):
                call_command("loaddata", str(source), stdout=StringIO())


class LoadProgramsCommandTestCase(TestCase):
    """Тесты загрузки справочника программ из XLSX."""

    headers = ("name", "direction", "is_active")

    def test_resolves_direction_and_upserts_by_name_and_direction(self) -> None:
        direction = DirectionFactory(name="Разработка", external_code="dev")
        with TemporaryDirectory() as directory:
            source = Path(directory) / "programs.xlsx"
            _write_workbook(source, self.headers, ("DevOps-инженер с нуля", "dev", None))

            call_command("loaddata", str(source), stdout=StringIO())

            program = Program.objects.get(name="DevOps-инженер с нуля")
            self.assertEqual(program.direction_id, direction.id)
            self.assertTrue(program.is_active)

            _write_workbook(source, self.headers, ("DevOps-инженер с нуля", "dev", "нет"))
            call_command("loaddata", str(source), stdout=StringIO())

            program.refresh_from_db()
            self.assertFalse(program.is_active)
            self.assertEqual(Program.objects.count(), 1)

    def test_unknown_direction_raises(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "programs.xlsx"
            _write_workbook(source, self.headers, ("Курс", "неизвестное направление", None))

            with self.assertRaises(CommandError):
                call_command("loaddata", str(source), stdout=StringIO())


class LoadReferenceDataCommandTestCase(TestCase):
    """Тесты флага --reference-data: загрузка всех справочников разом."""

    def test_loads_every_reference_book_in_dependency_order(self) -> None:
        with TemporaryDirectory() as base_dir:
            self._write_reference_data(Path(base_dir))

            with override_settings(BASE_DIR=Path(base_dir)):
                call_command("loaddata", "--reference-data", stdout=StringIO())

            self.assertEqual(Organization.objects.count(), 0)
            self.assertTrue(Vendor.objects.filter(external_code="vendor-1c").exists())
            self.assertTrue(Direction.objects.filter(external_code="dev").exists())

            program = Program.objects.get(name="DevOps-инженер с нуля")
            self.assertEqual(program.direction.external_code, "dev")

            # Продукты грузятся последними: вендор и программа уже созданы в этом же прогоне.
            product = Product.objects.get(external_code="product-1")
            self.assertEqual(product.vendor.external_code, "vendor-1c")
            self.assertCountEqual(product.programs.all(), [program])

    def test_missing_file_raises_and_loads_nothing(self) -> None:
        with TemporaryDirectory() as base_dir:
            self._write_reference_data(Path(base_dir))
            (Path(base_dir) / "reference_data" / "products.xlsx").unlink()

            with override_settings(BASE_DIR=Path(base_dir)), self.assertRaises(CommandError):
                call_command("loaddata", "--reference-data", stdout=StringIO())

            self.assertEqual(Vendor.objects.count(), 0)

    def test_broken_file_rolls_back_already_loaded_books(self) -> None:
        with TemporaryDirectory() as base_dir:
            directory = Path(base_dir) / "reference_data"
            self._write_reference_data(Path(base_dir))
            _write_workbook(
                directory / "products.xlsx",
                ("name", "external_code", "vendor"),
                ("Продукт", "product-1", "неизвестный вендор"),
            )

            with override_settings(BASE_DIR=Path(base_dir)), self.assertRaises(CommandError):
                call_command("loaddata", "--reference-data", stdout=StringIO())

            self.assertEqual(Vendor.objects.count(), 0)
            self.assertEqual(Direction.objects.count(), 0)
            self.assertEqual(Program.objects.count(), 0)

    def test_flag_with_explicit_file_raises(self) -> None:
        with self.assertRaises(CommandError):
            call_command("loaddata", "vendors.xlsx", "--reference-data", stdout=StringIO())

    def test_without_arguments_raises(self) -> None:
        with self.assertRaises(CommandError):
            call_command("loaddata", stdout=StringIO())

    def _write_reference_data(self, base_dir: Path) -> None:
        directory = base_dir / "reference_data"
        directory.mkdir()

        _write_workbook(directory / "organizations.xlsx", LoadOrganizationsCommandTestCase.headers)
        _write_workbook(directory / "vendors.xlsx", ("name", "external_code"), ("1С", "vendor-1c"))
        _write_workbook(directory / "directions.xlsx", ("name", "external_code"), ("Разработка", "dev"))
        _write_workbook(
            directory / "programs.xlsx",
            ("name", "direction"),
            ("DevOps-инженер с нуля", "dev"),
        )
        _write_workbook(
            directory / "products.xlsx",
            ("name", "external_code", "vendor", "programs"),
            ("1С:Предприятие", "product-1", "vendor-1c", "DevOps-инженер с нуля"),
        )
