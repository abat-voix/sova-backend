import io
from unittest import mock

import boto3
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.http import FileResponse, HttpResponseRedirect
from django.test import SimpleTestCase, TestCase, override_settings

from moto import mock_aws

from sova.core.api.exceptions import Gone
from sova.core.files import content_disposition_header, file_response
from sova.core.storage import s3_storage

_FAKE_CREDENTIALS = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_DEFAULT_REGION": "us-east-1",
}


class ContentDispositionHeaderTestCase(SimpleTestCase):
    """Имя файла в `Content-Disposition` кодируется по RFC 5987 (кириллица, пробелы)."""

    def test_attachment_encodes_non_ascii_name(self) -> None:
        header = content_disposition_header(True, "Договор Иванов.pdf")
        self.assertTrue(header.startswith("attachment; filename*=UTF-8''"))
        self.assertIn("%D0%94%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80", header)

    def test_inline_uses_inline_disposition(self) -> None:
        self.assertTrue(content_disposition_header(False, "a.pdf").startswith("inline;"))


class _FieldFileLike:
    """Минимальная замена `FieldFile`: только то, что использует `file_response`."""

    def __init__(self, storage, name: str) -> None:
        self.storage = storage
        self.name = name

    def open(self, mode: str = "rb"):
        return self.storage.open(self.name, mode)


class FileResponseProxyTestCase(TestCase):
    """`STORAGE_BACKEND=filesystem` (по умолчанию в тестах) — режим всегда proxy."""

    def test_streams_existing_file(self) -> None:
        storage = storages["default"]
        name = storage.save("check/a.txt", ContentFile(b"hello"))
        self.addCleanup(lambda: storage.delete(name))

        response = file_response(_FieldFileLike(storage, name), "a.txt")

        self.assertIsInstance(response, FileResponse)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_missing_file_returns_gone(self) -> None:
        storage = storages["default"]
        with self.assertRaises(Gone):
            file_response(_FieldFileLike(storage, "does/not/exist.txt"), "exist.txt")


@mock_aws
class FileResponseS3TestCase(TestCase):
    """Оба режима отдачи файла (`proxy`, `redirect`) на поднятом в памяти S3 (moto)."""

    def setUp(self) -> None:
        env_patch = mock.patch.dict("os.environ", _FAKE_CREDENTIALS)
        env_patch.start()
        self.addCleanup(env_patch.stop)

        self.client = boto3.client("s3", region_name="us-east-1")
        self.client.create_bucket(Bucket="sova-media-test")
        self.client.put_object(Bucket="sova-media-test", Key="a.pdf", Body=b"content")

        self.storage_override = override_settings(
            STORAGE_BACKEND="s3",
            STORAGES={
                "default": s3_storage("sova-media-test"),
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        self.storage_override.enable()
        self.addCleanup(self.storage_override.disable)

    def _field_file(self, name: str) -> _FieldFileLike:
        return _FieldFileLike(storages["default"], name)

    def test_proxy_mode_streams_file(self) -> None:
        with override_settings(S3_DOWNLOAD_MODE="proxy"):
            response = file_response(self._field_file("a.pdf"), "договор.pdf")
        self.assertIsInstance(response, FileResponse)

    def test_redirect_mode_returns_302_with_signed_url(self) -> None:
        with override_settings(S3_DOWNLOAD_MODE="redirect"):
            response = file_response(self._field_file("a.pdf"), "договор.pdf")
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(response.status_code, 302)
        self.assertIn("a.pdf", response.url)

    def test_redirect_mode_missing_file_returns_gone(self) -> None:
        with override_settings(S3_DOWNLOAD_MODE="redirect"), self.assertRaises(Gone):
            file_response(self._field_file("missing.pdf"), "missing.pdf")

    def test_proxy_mode_missing_file_returns_gone(self) -> None:
        with override_settings(S3_DOWNLOAD_MODE="proxy"), self.assertRaises(Gone):
            file_response(self._field_file("missing.pdf"), "missing.pdf")
