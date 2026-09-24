from pathlib import Path

from django.core.files import File
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    """
    Копирует уже загруженные файлы с диска в целевое хранилище (`default` или `reports`),
    без переименования — под тем же ключом, что уже записан в БД.

    Идёт по записям БД, а не по каталогу: так не подхватываются файлы-сироты, а команду можно
    безопасно повторять (пропускает то, что уже скопировано). См. runbook в
    docs/plans/2026-09-23-s3-storage.md, задача 11.
    """

    help = "Переносит файлы вложений/договоров/отчётов из STORAGE_BACKEND=filesystem в S3."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--source-root",
            required=True,
            help="Каталог на диске, где сейчас лежат файлы (MEDIA_ROOT или REPORTS_STORAGE_ROOT).",
        )
        parser.add_argument(
            "--storage",
            required=True,
            choices=["default", "reports"],
            help="Целевое хранилище из STORAGES (сейчас настроено — см. STORAGE_BACKEND).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только посчитать, ничего не загружать.",
        )

    def handle(self, *args, **options) -> None:
        source_root = Path(options["source_root"])
        storage_name = options["storage"]
        dry_run = options["dry_run"]
        storage = storages[storage_name]

        names = self._names_for(storage_name)
        copied = already_present = missing_source = 0

        for name in names:
            if not name:
                continue
            if storage.exists(name):
                already_present += 1
                continue

            source_path = source_root / name
            if not source_path.is_file():
                missing_source += 1
                self.stderr.write(f"Нет исходного файла: {source_path}")
                continue

            copied += 1
            if dry_run:
                continue
            with source_path.open("rb") as handle:
                saved_name = storage.save(name, File(handle))
            if saved_name != name:
                # get_available_name сработал бы только если файл уже существует в хранилище,
                # а мы это только что проверили — совпадение ключа гарантировано storage.save().
                raise CommandError(
                    f"Ключ изменился при копировании: {name!r} -> {saved_name!r}."
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Хранилище {storage_name!r}: скопировано {copied}, "
                f"уже было {already_present}, без исходника {missing_source}."
                + (" (dry-run)" if dry_run else "")
            )
        )

    def _names_for(self, storage_name: str) -> list[str]:
        if storage_name == "default":
            from sova.interactions.models import Contract, ContractFile
            from sova.processes.models import ActionAttachment

            return [
                *ActionAttachment.objects.exclude(file="").values_list("file", flat=True),
                *Contract.objects.exclude(file="").values_list("file", flat=True),
                *ContractFile.objects.exclude(file="").values_list("file", flat=True),
            ]

        from sova.reports.models import ReportJob

        return list(
            ReportJob.objects.filter(status="ready", expires_at__gt=timezone.now())
            .exclude(file="")
            .values_list("file", flat=True)
        )
