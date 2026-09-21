import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


BASE_DIR = Path(__file__).resolve().parent.parent
SMTP_ENVIRONMENT_VARIABLES = (
    "EMAIL_HOST",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD",
)


class SettingsTests(SimpleTestCase):
    def run_django_check_without_smtp(
        self, environment_name: str
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        for variable_name in SMTP_ENVIRONMENT_VARIABLES:
            environment.pop(variable_name, None)
        environment.update(
            {
                "ENVIRONMENT": environment_name,
                "DJANGO_SECRET_KEY": "test-only-secret-key",
                "DATABASE_URL": "sqlite:///:memory:",
            }
        )

        return subprocess.run(
            [sys.executable, BASE_DIR / "manage.py", "check"],
            cwd=BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_django_commands_work_without_smtp_in_testing(self) -> None:
        result = self.run_django_check_without_smtp("testing")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_requires_smtp_configuration(self) -> None:
        result = self.run_django_check_without_smtp("production")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "EMAIL_HOST, EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be set",
            result.stderr,
        )
