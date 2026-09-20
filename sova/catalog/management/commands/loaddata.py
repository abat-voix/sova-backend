from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.loaddata import Command as DjangoLoadDataCommand
from django.db import transaction
from openpyxl import load_workbook

from sova.catalog.models import University
from sova.catalog.models.university import InstitutionType


class Command(DjangoLoadDataCommand):
    help = "Загружает Django fixtures или справочники XLSX из reference_data."

    def handle(self, *fixture_labels, **options):
        source = self._resolve_xlsx(fixture_labels)
        if source is None:
            return super().handle(*fixture_labels, **options)

        self._load_universities(source)

    def _resolve_xlsx(self, fixture_labels: tuple[str, ...]) -> Path | None:
        if len(fixture_labels) != 1:
            return None

        label = Path(fixture_labels[0])
        if label.suffix.lower() != ".xlsx":
            return None

        candidates = [label]
        if not label.is_absolute():
            candidates.append(Path(settings.BASE_DIR) / "reference_data" / label.name)

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        raise CommandError(f"Файл справочника не найден: {fixture_labels[0]}")

    @transaction.atomic
    def _load_universities(self, source: Path) -> None:
        if source.name != "universities.xlsx":
            raise CommandError(f"Неизвестный XLSX-справочник: {source.name}")

        workbook = load_workbook(source, read_only=True, data_only=True)
        worksheet = workbook.active
        rows = worksheet.iter_rows(values_only=True)

        try:
            raw_headers = next(rows)
        except StopIteration as error:
            raise CommandError("Файл universities.xlsx пуст.") from error

        headers = [str(value).strip() if value is not None else "" for value in raw_headers]
        required = {
            "id",
            "ror",
            "name_en",
            "name",
            "country_code",
            "type",
            "works_count",
            "cited_by_count",
            "city",
            "region",
            "lat",
            "lon",
            "homepage_url",
        }
        missing = sorted(required - set(headers))
        if missing:
            raise CommandError(f"В universities.xlsx отсутствуют колонки: {', '.join(missing)}")

        created = 0
        updated = 0
        allowed_types = {value for value, _label in InstitutionType.choices}

        for row_number, values in enumerate(rows, start=2):
            if not any(value not in (None, "") for value in values):
                continue

            row = dict(zip(headers, values, strict=False))
            try:
                name = self._text(row["name"])
                if not name:
                    raise ValueError("поле name обязательно")

                external_code = self._text(row["ror"]) or self._text(row["id"])
                if not external_code:
                    raise ValueError("должно быть заполнено поле ror или id")

                institution_type = self._text(row["type"]).lower() or InstitutionType.EDUCATION
                if institution_type not in allowed_types:
                    raise ValueError(f"неизвестный type: {institution_type}")

                defaults = {
                    "name": name,
                    "name_en": self._text(row["name_en"]),
                    "institution_type": institution_type,
                    "country_code": self._text(row["country_code"]).upper(),
                    "region": self._text(row["region"]),
                    "city": self._text(row["city"]),
                    "lat": self._decimal(row["lat"]),
                    "lon": self._decimal(row["lon"]),
                    "works_count": self._positive_int(row["works_count"]),
                    "cited_by_count": self._positive_int(row["cited_by_count"]),
                    "homepage_url": self._text(row["homepage_url"]),
                }
            except (InvalidOperation, TypeError, ValueError) as error:
                raise CommandError(f"Ошибка в строке {row_number}: {error}") from error

            university = University.objects.filter(external_code=external_code).first()
            if university is None:
                university = University.objects.filter(name=name).first()

            if university is None:
                University.objects.create(external_code=external_code, **defaults)
                created += 1
            else:
                university.external_code = external_code
                for field, value in defaults.items():
                    setattr(university, field, value)
                university.save(update_fields=["external_code", *defaults, "updated_at"])
                updated += 1

        workbook.close()
        self.stdout.write(
            self.style.SUCCESS(f"Справочник вузов загружен: создано {created}, обновлено {updated}.")
        )

    @staticmethod
    def _text(value) -> str:
        return "" if value is None else str(value).strip()

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))

    @staticmethod
    def _positive_int(value) -> int:
        if value in (None, ""):
            return 0
        number = Decimal(str(value))
        if number < 0 or number != number.to_integral_value():
            raise ValueError(f"ожидалось целое неотрицательное число, получено {value}")
        return int(number)
