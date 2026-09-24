from celery import shared_task
from django.conf import settings

from sova.reports.services import jobs


@shared_task(
    bind=True,
    acks_late=True,
    autoretry_for=(jobs.RetryableReportError,),
    retry_backoff=30,
    max_retries=5,
    soft_time_limit=settings.REPORTS_JOB_TIMEOUT_SECONDS,
    time_limit=settings.REPORTS_JOB_TIMEOUT_SECONDS + 60,
)
def build_report_job(self, job_id: str) -> None:
    """Строит файл отчёта по заданию `ReportJob`."""
    jobs.run_job(job_id)


@shared_task
def cleanup_report_jobs() -> dict:
    """Удаляет просроченные файлы и закрывает зависшие задания."""
    return jobs.cleanup_jobs()
