from django.db import models

from sova.core.files import uuid_upload_to
from sova.core.models import TimeStampedModel
from sova.interactions.enum import DocumentTemplateKind


class DocumentTemplate(TimeStampedModel):
    """
    Шаблон документа (.docx) для рендера через docxtpl.

    Фронтенд собирает JSON с данными документа, бэкенд подставляет его в `file` и сохраняет
    результат как файл сущности (для `CONTRACT` — `Contract.file`). Пока рендер не подключён:
    данные принимаются, файл не создаётся — поэтому `file` необязателен.
    """

    name = models.CharField(
        max_length=255,
        verbose_name="Название",
    )
    kind = models.CharField(
        max_length=50,
        choices=DocumentTemplateKind.choices,
        verbose_name="Тип документа",
    )
    file = models.FileField(
        upload_to=uuid_upload_to("document_templates"),
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Файл шаблона (.docx)",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    class Meta:
        verbose_name = "Шаблон документа"
        verbose_name_plural = "Шаблоны документов"
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.name}"
