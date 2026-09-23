"""Жизненный цикл заданий на выгрузку: создание, выполнение, очистка."""

from __future__ import annotations

import logging
import tempfile
from datetime import timedelta

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone

from reports.pdf import PDFGenerationError
from sova.reports.enum import ReportJobStatus
from sova.reports.models import ReportJob
from sova.reports.services.dataset import ReportDataset
from sova.reports.services.exporters import ReportTooLargeError, export
from sova.reports.spec import ReportSpec

logger = logging.getLogger(__name__)

FILE_EXTENSIONS = {"xlsx": "xlsx", "xls": "xls", "pdf": "pdf", "json": "json"}


class RetryableReportError(RuntimeError):
    """Временная ошибка (например, недоступен Gotenberg): задание можно повторить."""


def create_job(owner, spec: ReportSpec) -> ReportJob:
    """Создаёт задание и ставит его в очередь после фиксации транзакции."""
    from sova.reports.tasks import build_report_job

    job = ReportJob.objects.create(owner=owner, spec=spec.to_dict(), format=spec.format)
    transaction.on_commit(lambda: build_report_job.delay(str(job.pk)))
    return job


def run_job(job_id) -> None:
    """
    Выполняет задание. Повторный запуск уже взятого или завершённого задания ничего не делает,
    поэтому повторная доставка сообщения брокером безопасна.
    """
    with transaction.atomic():
        job = ReportJob.objects.select_for_update().select_related("owner").filter(pk=job_id).first()
        if job is None or job.status != ReportJobStatus.QUEUED:
            return
        job.status = ReportJobStatus.RUNNING
        job.started_at = timezone.now()
        job.attempts += 1
        job.save(update_fields=["status", "started_at", "attempts"])

    spec = ReportSpec.from_dict(job.spec)
    # Видимость пересчитывается по текущей роли владельца, а не берётся из запроса
    dataset = ReportDataset(user=job.owner, spec=spec)
    counting = _CountingDataset(dataset)
    try:
        with tempfile.TemporaryFile() as out:
            export(counting, job.format, out)
            out.seek(0)
            filename = f"report-{timezone.localtime(dataset.generated_at):%Y%m%d-%H%M%S}.{FILE_EXTENSIONS[job.format]}"
            job.file.save(filename, File(out), save=False)
    except ReportTooLargeError as error:
        _fail(job, "too_large", str(error))
        return
    except PDFGenerationError as error:
        logger.warning("Report job %s: PDF generation failed: %s", job.pk, error)
        if job.attempts < settings.REPORTS_MAX_ATTEMPTS:
            job.status = ReportJobStatus.QUEUED
            job.save(update_fields=["status"])
            raise RetryableReportError(str(error)) from error
        _fail(job, "pdf_unavailable", "Сервис формирования PDF недоступен. Повторите позже.")
        return
    except Exception:
        logger.exception("Report job %s failed", job.pk)
        _fail(job, "internal_error", "Не удалось построить отчёт.")
        return

    now = timezone.now()
    job.status = ReportJobStatus.READY
    job.finished_at = now
    job.expires_at = now + timedelta(hours=settings.REPORTS_RETENTION_HOURS)
    job.file_size = job.file.size
    job.rows_count = counting.rows_count
    job.save(update_fields=["status", "finished_at", "expires_at", "file", "file_size", "rows_count"])


def _fail(job: ReportJob, code: str, message: str) -> None:
    if job.file:
        job.file.delete(save=False)
    job.status = ReportJobStatus.FAILED
    job.finished_at = timezone.now()
    job.error_code = code
    job.error_message = message[:500]
    job.save(update_fields=["status", "finished_at", "error_code", "error_message", "file"])


class _CountingDataset:
    """Обёртка над выборкой, считающая выданные строки без повторного запроса."""

    def __init__(self, dataset: ReportDataset):
        self._dataset = dataset
        self.rows_count = 0

    def __getattr__(self, name):
        return getattr(self._dataset, name)

    def iter_rows(self):
        for row in self._dataset.iter_rows():
            self.rows_count += 1
            yield row


def cleanup_jobs() -> dict:
    """
    Удаляет файлы с истёкшим сроком хранения и помечает ошибкой зависшие задания,
    чтобы они не висели в `queued/running` бесконечно.
    """
    now = timezone.now()
    expired = 0
    for job in ReportJob.objects.filter(status=ReportJobStatus.READY, expires_at__lt=now).iterator():
        job.file.delete(save=False)
        job.delete()
        expired += 1

    stale_before = now - timedelta(seconds=settings.REPORTS_JOB_TIMEOUT_SECONDS)
    stale = ReportJob.objects.filter(
        status__in=(ReportJobStatus.QUEUED, ReportJobStatus.RUNNING),
        created_at__lt=stale_before,
    ).update(
        status=ReportJobStatus.FAILED,
        finished_at=now,
        error_code="timeout",
        error_message="Превышено время построения отчёта.",
    )

    failed_before = now - timedelta(hours=settings.REPORTS_RETENTION_HOURS)
    failed, _ = ReportJob.objects.filter(status=ReportJobStatus.FAILED, finished_at__lt=failed_before).delete()
    return {"expired": expired, "stale": stale, "failed_deleted": failed}
