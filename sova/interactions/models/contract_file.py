from django.conf import settings
from django.db import models

from sova.core.files import uuid_upload_to
from sova.core.models import UUIDModel


class ContractFile(UUIDModel):
    """
    Файл, загруженный к договору — журнал: запись создаётся системой при каждой загрузке
    файла в `Contract.file`, вручную не редактируется и не удаляется.

    `Contract.file` — ссылка только на текущий файл; при повторной загрузке (создание
    договора, корректировка, подписание — см. `sova.workflows.presets`) ссылка заменяется,
    но история не теряется: старые файлы остаются доступны через этот журнал (П9 «история
    не удаляется»). Новая запись указывает на тот же ключ хранилища, что и `Contract.file`
    в момент загрузки — файл не копируется.
    """

    contract = models.ForeignKey(
        to="interactions.Contract",
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name="Договор",
    )
    file = models.FileField(
        upload_to=uuid_upload_to("contracts"),
        max_length=500,
        verbose_name="Файл",
    )
    original_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Исходное имя файла",
    )
    size = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        verbose_name="Размер файла, байт",
    )
    content_type = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="MIME-тип",
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Загружен",
    )
    uploaded_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="contract_files",
        null=True,
        blank=True,
        verbose_name="Кто загрузил",
    )

    class Meta:
        verbose_name = "Файл договора"
        verbose_name_plural = "Файлы договора"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_name or self.file.name
