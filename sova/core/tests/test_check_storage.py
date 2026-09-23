import io
from unittest import mock

import boto3
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from moto import mock_aws

from sova.core.storage import s3_storage

_FAKE_CREDENTIALS = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_DEFAULT_REGION": "us-east-1",
}


@mock_aws
class CheckStorageS3TestCase(TestCase):
    """`check_storage` на поднятом в памяти S3 (moto)."""

    def setUp(self) -> None:
        env_patch = mock.patch.dict("os.environ", _FAKE_CREDENTIALS)
        env_patch.start()
        self.addCleanup(env_patch.stop)

        self.client = boto3.client("s3", region_name="us-east-1")
        self.client.create_bucket(Bucket="sova-media-test")
        self.client.create_bucket(Bucket="sova-reports-test")

        storages_override = override_settings(
            STORAGE_BACKEND="s3",
            STORAGES={
                "default": s3_storage("sova-media-test"),
                "reports": s3_storage("sova-reports-test", location="reports"),
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        storages_override.enable()
        self.addCleanup(storages_override.disable)

    def test_ok_when_buckets_reachable(self) -> None:
        """Оба бакета существуют и доступны — команда завершается без ошибок."""
        call_command("check_storage", stdout=io.StringIO())

    def test_fails_with_clear_message_when_bucket_missing(self) -> None:
        """Несуществующий бакет — понятная ошибка, а не сырое исключение boto3."""
        storages_override = override_settings(
            STORAGES={
                "default": s3_storage("does-not-exist"),
                "reports": s3_storage("sova-reports-test", location="reports"),
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        )
        storages_override.enable()
        self.addCleanup(storages_override.disable)

        with self.assertRaises(CommandError) as ctx:
            call_command("check_storage", stdout=io.StringIO())
        self.assertIn("default", str(ctx.exception))

    def test_apply_lifecycle_sets_expiration_rule(self) -> None:
        """`--apply-lifecycle` ставит на бакет reports правило автоудаления по префиксу."""
        with override_settings(REPORTS_RETENTION_HOURS=72):
            call_command("check_storage", "--apply-lifecycle", stdout=io.StringIO())

        config = self.client.get_bucket_lifecycle_configuration(Bucket="sova-reports-test")
        rule = config["Rules"][0]
        self.assertEqual(rule["Filter"]["Prefix"], "reports/")
        self.assertEqual(rule["Expiration"]["Days"], 4)
        self.assertEqual(rule["AbortIncompleteMultipartUpload"]["DaysAfterInitiation"], 1)


class CheckStorageFilesystemTestCase(TestCase):
    """При `STORAGE_BACKEND=filesystem` команда проверяет обычные каталоги и не трогает S3."""

    def test_ok_on_filesystem(self) -> None:
        call_command("check_storage", stdout=io.StringIO())

    def test_apply_lifecycle_is_noop_on_filesystem(self) -> None:
        out = io.StringIO()
        call_command("check_storage", "--apply-lifecycle", stdout=out)
        self.assertIn("не применяется", out.getvalue())
