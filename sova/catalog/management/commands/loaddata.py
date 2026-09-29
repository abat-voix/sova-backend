from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.loaddata import Command as DjangoLoadDataCommand
from django.db import transaction

from sova.catalog.exceptions import CatalogImportError
from sova.catalog.enum import CatalogType
from sova.catalog.services import catalog_import_service


VENDOR_REFERENCE_HEADER_ALIASES = {
    "Компания": "name",
    "Продукт": "products",
    "ФИО": "contact_full_name",
    "Телефон": "contact_phone",
    "Почта": "contact_email",
    "Способ связи": "contact_channels",
}


class Command(DjangoLoadDataCommand):
    help = "Загружает Django fixtures или справочники XLSX из reference_data."

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        # Django объявляет метки фикстур обязательными (nargs="+"), но с --reference-data
        # указывать их не нужно: ослабляем до nargs="*" и проверяем комбинацию сами.
        for action in parser._actions:
            if action.dest == "args":
                action.nargs = "*"
                break
        parser.add_argument(
            "--reference-data",
            action="store_true",
            help=(
                "Загрузить все справочники XLSX из reference_data "
                "в порядке зависимостей, без указания файлов."
            ),
        )

    def handle(self, *fixture_labels, **options):
        if options.pop("reference_data", False):
            if fixture_labels:
                raise CommandError("--reference-data нельзя совмещать с указанием файлов.")
            return self._load_reference_data()

        if not fixture_labels:
            raise CommandError(self.missing_args_message)

        source = self._resolve_xlsx(fixture_labels)
        if source is None:
            return super().handle(*fixture_labels, **options)

        loader = self._loaders().get(source.name)
        if loader is None:
            raise CommandError(f"Неизвестный XLSX-справочник: {source.name}")
        loader(source)

    def _loaders(self) -> dict:
        """Справочники в порядке зависимостей: продукты ссылаются на вендоров и программы."""
        return {
            "organizations.xlsx": self._load_organizations,
            "vendors.xlsx": self._load_vendors,
            "directions.xlsx": self._load_directions,
            "programs.xlsx": self._load_programs,
            "products.xlsx": self._load_products,
        }

    @transaction.atomic
    def _load_reference_data(self) -> None:
        directory = Path(settings.BASE_DIR) / "reference_data"
        loaders = self._loaders()

        missing = [name for name in loaders if not (directory / name).is_file()]
        if missing:
            raise CommandError(f"В {directory} не найдены справочники: {', '.join(missing)}")

        for name, loader in loaders.items():
            loader(directory / name)

        self.stdout.write(self.style.SUCCESS(f"Загружены все справочники: {', '.join(loaders)}."))

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

    def _load_organizations(self, source: Path) -> None:
        self._run_loader(source, CatalogType.ORGANIZATION, "организаций")

    def _load_vendors(self, source: Path) -> None:
        self._run_loader(
            source,
            CatalogType.VENDOR,
            "вендоров",
            header_aliases=VENDOR_REFERENCE_HEADER_ALIASES,
        )

    def _load_directions(self, source: Path) -> None:
        self._run_loader(source, CatalogType.DIRECTION, "направлений")

    def _load_products(self, source: Path) -> None:
        self._run_loader(source, CatalogType.PRODUCT, "продуктов")

    def _load_programs(self, source: Path) -> None:
        self._run_loader(source, CatalogType.PROGRAM, "программ")

    def _run_loader(
        self,
        source: Path,
        catalog_type: str,
        label: str,
        header_aliases: dict[str, str] | None = None,
    ) -> None:
        """CLI читает файл с фиксированными заголовками (без CatalogImportMapping) и вызывает сервис импорта."""
        try:
            result = catalog_import_service.import_canonical_file(
                catalog_type=catalog_type,
                source=source,
                header_aliases=header_aliases,
            )
        except CatalogImportError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(f"Справочник {label} загружен: создано {result.created}, обновлено {result.updated}.")
        )
        for warning in result.warnings:
            self.stdout.write(self.style.WARNING(str(warning)))
