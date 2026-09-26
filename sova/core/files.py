"""
Общие помощники для полей `FileField`: ключи объектов, ограничение размера и отдача файла
через API (см. `docs/plans/2026-09-23-s3-storage.md`).
"""

import mimetypes
import os
import uuid
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import FileResponse, HttpResponseRedirect
from django.utils.deconstruct import deconstructible
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext_lazy as _

from sova.core.api.exceptions import Gone


# Единый согласованный список для пользовательских файлов (действия и сообщения).
ALLOWED_ATTACHMENT_EXTENSIONS = (
    "png", "jpg", "jpeg", "pdf", "zip", "gz", "gzip", "rar", "doc", "docx", "xls", "xlsx",
)


@deconstructible
class uuid_upload_to:  # noqa: N801 — используется как `upload_to=uuid_upload_to("...")`, не как класс
    """
    `upload_to` с ключом на основе UUID: `<prefix>/%Y/%m/<uuid4><ext>`.

    Ключ не содержит исходного имени файла (кириллица, пробелы, повторы не всплывают в
    хранилище) — исходное имя хранится отдельно, в поле модели `original_name`/`file_name`.
    Реализовано как `@deconstructible`-класс, а не замыкание: Django должен суметь
    сериализовать `upload_to` в миграции, а обычную замкнутую функцию он не сериализует.
    """

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def __call__(self, instance, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        today = datetime.now()
        return f"{self.prefix}/{today:%Y/%m}/{uuid.uuid4()}{ext}"


def guess_content_type(filename: str) -> str:
    """Определяет MIME-тип по расширению — не по заголовку, присланному клиентом."""
    content_type, _encoding = mimetypes.guess_type(filename)
    return content_type or "application/octet-stream"


def content_disposition_header(as_attachment: bool, filename: str) -> str:
    """`Content-Disposition` с именем файла в кодировке RFC 5987 (кириллица, пробелы)."""
    disposition = "attachment" if as_attachment else "inline"
    return f"{disposition}; filename*=UTF-8''{escape_uri_path(filename)}"


def file_response(field_file, filename: str, *, content_type: str | None = None, inline: bool = False):
    """
    Отдаёт файл авторизованному запросу — прокси или редирект, в зависимости от
    `settings.S3_DOWNLOAD_MODE` (см. решение №4 плана):

    - `filesystem`/`proxy`: Django сам стримит файл (`FileResponse`); хранилище остаётся
      только во внутренней сети, наружу не публикуется;
    - `redirect` (только `STORAGE_BACKEND=s3`): `302` на подписанный URL с TTL
      `S3_PRESIGNED_TTL`, у которого уже выставлен нужный `Content-Disposition` —
      скачивание видит исходное имя файла, а не случайный ключ в хранилище.

    Отсутствующий в хранилище файл (удалён вручную, не пережил перенос) — `Gone` (410), а не
    500: с точки зрения API это тот же случай, что и просроченный отчёт.
    """
    content_type = content_type or guess_content_type(filename)
    redirect = settings.STORAGE_BACKEND == "s3" and settings.S3_DOWNLOAD_MODE == "redirect"

    if redirect:
        # generate_presigned_url не проверяет существование объекта — проверяем сами, иначе
        # клиент вместо понятного 410 от нашего API получит сырую XML-ошибку от S3 после 302.
        if not field_file.storage.exists(field_file.name):
            raise Gone()
        url = field_file.storage.url(
            field_file.name,
            parameters={
                "ResponseContentDisposition": content_disposition_header(not inline, filename),
                "ResponseContentType": content_type,
            },
        )
        response = HttpResponseRedirect(url)
    else:
        try:
            handle = field_file.open("rb")
        except FileNotFoundError as exc:
            raise Gone() from exc
        response = FileResponse(
            handle,
            as_attachment=not inline,
            filename=filename,
            content_type=content_type,
        )

    response["Cache-Control"] = "private, no-store"
    return response


def validate_file_size(uploaded_file) -> None:
    """Валидатор `FileField`/`serializers.FileField`: отклоняет файлы больше `FILE_UPLOAD_MAX_SIZE`."""
    max_size = settings.FILE_UPLOAD_MAX_SIZE
    if uploaded_file.size > max_size:
        raise ValidationError(
            _("Файл слишком большой: %(size).1f МБ, максимум %(max)d МБ.")
            % {"size": uploaded_file.size / 1024 / 1024, "max": max_size // 1024 // 1024},
            code="file_too_large",
        )
