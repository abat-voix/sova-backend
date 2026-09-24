from unittest import mock

from django.test import SimpleTestCase

from sova.core.storage import s3_storage


class S3StorageConfigTestCase(SimpleTestCase):
    """`s3_storage()` собирает OPTIONS из переменных окружения `S3_*`."""

    def test_defaults_without_env(self) -> None:
        """Без переменных окружения — только обязательные поля, остальные пусты/по умолчанию."""
        with mock.patch.dict("os.environ", {}, clear=True):
            config = s3_storage("sova-media")

        self.assertEqual(config["BACKEND"], "storages.backends.s3.S3Storage")
        options = config["OPTIONS"]
        self.assertEqual(options["bucket_name"], "sova-media")
        self.assertEqual(options["location"], "")
        self.assertIsNone(options["endpoint_url"])
        self.assertIsNone(options["region_name"])
        self.assertIsNone(options["access_key"])
        self.assertIsNone(options["secret_key"])
        self.assertEqual(options["addressing_style"], "path")
        self.assertEqual(options["signature_version"], "s3v4")
        self.assertIsNone(options["default_acl"])
        self.assertFalse(options["file_overwrite"])
        self.assertTrue(options["querystring_auth"])
        self.assertEqual(options["querystring_expire"], 300)

    def test_reads_env_and_location(self) -> None:
        """Переменные окружения и `location` (префикс ключей) попадают в OPTIONS."""
        env = {
            "S3_ENDPOINT_URL": "http://s3:3900",
            "S3_REGION": "garage",
            "S3_ACCESS_KEY_ID": "GKexample",
            "S3_SECRET_ACCESS_KEY": "secret",
            "S3_ADDRESSING_STYLE": "virtual",
            "S3_PRESIGNED_TTL": "60",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            config = s3_storage("sova-reports", location="reports")

        options = config["OPTIONS"]
        self.assertEqual(options["bucket_name"], "sova-reports")
        self.assertEqual(options["location"], "reports")
        self.assertEqual(options["endpoint_url"], "http://s3:3900")
        self.assertEqual(options["region_name"], "garage")
        self.assertEqual(options["access_key"], "GKexample")
        self.assertEqual(options["secret_key"], "secret")
        self.assertEqual(options["addressing_style"], "virtual")
        self.assertEqual(options["querystring_expire"], 60)
