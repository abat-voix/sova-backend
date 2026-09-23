import math
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """
    Проверяет, что хранилища `default` и `reports` доступны на чтение/запись/удаление.

    Одна команда для обоих провайдеров (Garage или внешний S3) и для локального
    `STORAGE_BACKEND=filesystem`. Вызывается из `deploy.sh` после старта хранилища —
    деплой должен упасть сразу, если хранилище недоступно, а не при первой загрузке файла.
    """

    help = "Проверяет доступность файловых хранилищ default/reports; см. --apply-lifecycle."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--apply-lifecycle",
            action="store_true",
            help=(
                "Дополнительно поставить на бакет reports правило автоудаления "
                "просроченных отчётов (страховка к cleanup_report_jobs). Игнорируется "
                "при STORAGE_BACKEND=filesystem."
            ),
        )

    def handle(self, *args, **options) -> None:
        for name in ("default", "reports"):
            self._check_storage(name)
            self.stdout.write(self.style.SUCCESS(f"Хранилище {name!r}: доступно."))

        if options["apply_lifecycle"]:
            if settings.STORAGE_BACKEND != "s3":
                self.stdout.write("STORAGE_BACKEND=filesystem — lifecycle не применяется.")
            else:
                self._apply_reports_lifecycle()
                self.stdout.write(self.style.SUCCESS("Lifecycle на бакете reports обновлён."))

    def _check_storage(self, name: str) -> None:
        """Записывает, читает и удаляет служебный объект `.healthcheck/<uuid>`."""
        storage = storages[name]
        check_name = f".healthcheck/{uuid.uuid4()}"
        try:
            saved_name = storage.save(check_name, ContentFile(b"check_storage"))
        except Exception as exc:  # noqa: BLE001 — сообщение важнее конкретного типа исключения
            raise CommandError(
                f"Хранилище {name!r} недоступно на запись: {exc}. "
                "Проверьте STORAGE_BACKEND, S3_ENDPOINT_URL, S3_REGION, ключи доступа и "
                "существование бакета."
            ) from exc

        try:
            with storage.open(saved_name, "rb") as handle:
                if handle.read() != b"check_storage":
                    raise CommandError(f"Хранилище {name!r}: прочитанные данные не совпадают.")
        except CommandError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Хранилище {name!r} недоступно на чтение: {exc}.") from exc
        finally:
            storage.delete(saved_name)

    def _apply_reports_lifecycle(self) -> None:
        """
        Правило автоудаления на бакет `reports`: страховка к celery-очистке
        `cleanup_report_jobs`, а не замена ей — задание может быть выполнено, но так и не
        удалено (сбой воркера, ручная правка), и тогда файл остаётся в бакете навсегда.
        """
        storage = storages["reports"]
        client = storage.connection.meta.client
        expiration_days = math.ceil(settings.REPORTS_RETENTION_HOURS / 24) + 1

        client.put_bucket_lifecycle_configuration(
            Bucket=storage.bucket_name,
            LifecycleConfiguration={
                "Rules": [
                    {
                        "ID": "sova-reports-expiration",
                        "Status": "Enabled",
                        "Filter": {"Prefix": "reports/"},
                        "Expiration": {"Days": expiration_days},
                        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
                    },
                ],
            },
        )
