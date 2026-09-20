from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from openpyxl import Workbook

from sova.catalog.models import University


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
