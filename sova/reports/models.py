from django.conf import settings
from django.core.files.storage import storages
from django.db import models

from sova.core.models import UUIDModel
from sova.reports.enum import ReportFormat, ReportJobStatus, ReportType


def reports_storage():
    """Приватное хранилище готовых файлов, общее для API и worker (`STORAGES["reports"]`)."""
    return storages["reports"]


def report_upload_to(instance: "ReportJob", filename: str) -> str:
    return f"{instance.created_at:%Y/%m}/{instance.pk}/{filename}"


class ReportJob(UUIDModel):
    """
    Задание на построение файла отчёта.

    Хранит нормализованный `ReportSpec`: worker строит отчёт заново от имени владельца
    с его текущей видимостью взаимодействий, не доверяя идентификаторам из запроса.
    """

    owner = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="report_jobs",
        verbose_name="Владелец",
    )
    report_type = models.CharField(
        max_length=32,
        choices=ReportType.choices,
        default=ReportType.INTERACTIONS,
        verbose_name="Тип отчёта",
    )
    spec = models.JSONField(verbose_name="Параметры отчёта")
    format = models.CharField(
        max_length=8,
        choices=ReportFormat.choices,
        verbose_name="Формат",
    )
    status = models.CharField(
        max_length=16,
        choices=ReportJobStatus.choices,
        default=ReportJobStatus.QUEUED,
        verbose_name="Состояние",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Начато")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершено")
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Хранится до")
    file = models.FileField(
        storage=reports_storage,
        upload_to=report_upload_to,
        max_length=500,
        blank=True,
        verbose_name="Файл",
    )
    file_size = models.PositiveBigIntegerField(null=True, blank=True, verbose_name="Размер файла, байт")
    rows_count = models.PositiveIntegerField(null=True, blank=True, verbose_name="Число строк")
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name="Попыток")
    error_code = models.CharField(max_length=64, blank=True, verbose_name="Код ошибки")
    error_message = models.CharField(max_length=500, blank=True, verbose_name="Сообщение об ошибке")

    class Meta:
        verbose_name = "Задание на отчёт"
        verbose_name_plural = "Задания на отчёты"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"], name="report_job_owner_idx"),
            models.Index(fields=["status", "expires_at"], name="report_job_status_idx"),
        ]

    def __str__(self):
        return f"{self.get_report_type_display()} ({self.format}) — {self.get_status_display()}"
