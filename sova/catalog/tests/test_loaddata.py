from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command
from django.test import TestCase
from openpyxl import Workbook

from sova.catalog.models import Direction, Product, Program, University, Vendor
from sova.catalog.tests.factories import DirectionFactory, ProgramFactory, VendorFactory


class LoadUniversitiesCommandTestCase(TestCase):
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
            source = Path(directory) / "universities.xlsx"
            self._save_workbook(source, short_name="МГУ")

            call_command("loaddata", str(source), stdout=StringIO())

            university = University.objects.get(external_code="https://ror.org/test")
            self.assertEqual(university.short_name, "МГУ")

            self._save_workbook(source, short_name="МГУ имени М. В. Ломоносова")
            call_command("loaddata", str(source), stdout=StringIO())

            university.refresh_from_db()
            self.assertEqual(
                university.short_name,
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
                "Lomonosov Moscow State University",
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
