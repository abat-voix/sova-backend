import io
from unittest import mock

import boto3
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from moto import mock_aws

from sova.core.storage import s3_storage
from sova.core.tests.media import TemporaryMediaMixin
from sova.interactions.tests.factories import ContractFactory
from sova.processes.tests.factories import ActionAttachmentFactory

_FAKE_CREDENTIALS = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_DEFAULT_REGION": "us-east-1",
}


@mock_aws
class CopyFilesToStorageTestCase(TemporaryMediaMixin, TestCase):
    """`copy_files_to_storage` переносит файлы из локального MEDIA_ROOT в S3 (moto)."""

    def setUp(self) -> None:
        env_patch = mock.patch.dict("os.environ", _FAKE_CREDENTIALS)
        env_patch.start()
        self.addCleanup(env_patch.stop)

        self.client = boto3.client("s3", region_name="us-east-1")
        self.client.create_bucket(Bucket="sova-media-test")

        # Файлы создаются во временном MEDIA_ROOT (filesystem — текущий STORAGE_BACKEND).
        self.attachment = ActionAttachmentFactory(file=ContentFile(b"a", name="a.pdf"))
        self.contract = ContractFactory(file=ContentFile(b"c", name="c.pdf"))

    def _target_storage_override(self):
        return override_settings(
            STORAGES={
                "default": s3_storage("sova-media-test"),
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )

    def test_copies_files_and_is_idempotent(self) -> None:
        source_root = self._media_dir.name

        with self._target_storage_override():
            out = io.StringIO()
            call_command(
                "copy_files_to_storage",
                f"--source-root={source_root}",
                "--storage=default",
                stdout=out,
            )
            self.assertIn("скопировано 2", out.getvalue())
            self.assertIn("уже было 0", out.getvalue())

            keys = {
                obj["Key"]
                for obj in self.client.list_objects_v2(Bucket="sova-media-test").get("Contents", [])
            }
            self.assertIn(self.attachment.file.name, keys)
            self.assertIn(self.contract.file.name, keys)

            out2 = io.StringIO()
            call_command(
                "copy_files_to_storage",
                f"--source-root={source_root}",
                "--storage=default",
                stdout=out2,
            )
            self.assertIn("скопировано 0", out2.getvalue())
            self.assertIn("уже было 2", out2.getvalue())

    def test_dry_run_does_not_upload(self) -> None:
        with self._target_storage_override():
            out = io.StringIO()
            call_command(
                "copy_files_to_storage",
                f"--source-root={self._media_dir.name}",
                "--storage=default",
                "--dry-run",
                stdout=out,
            )
            self.assertIn("скопировано 2", out.getvalue())
            self.assertIn("(dry-run)", out.getvalue())
            objects = self.client.list_objects_v2(Bucket="sova-media-test").get("Contents", [])
            self.assertEqual(objects, [])
