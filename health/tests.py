from django.test import TestCase
from django.urls import reverse


class HealthViewTests(TestCase):
    def test_health_returns_dependency_status(self) -> None:
        response = self.client.get(reverse("health"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "database": "ok", "cache": "ok"},
        )

    def test_health_only_accepts_get(self) -> None:
        response = self.client.post(reverse("health"))

        self.assertEqual(response.status_code, 405)


class ApiDocumentationTests(TestCase):
    def test_openapi_schema_is_public_and_contains_health_endpoint(self) -> None:
        response = self.client.get(reverse("schema"), HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["openapi"], "3.0.3")
        self.assertIn("/api/health/", response.json()["paths"])

    def test_swagger_ui_is_public(self) -> None:
        response = self.client.get(reverse("swagger-ui"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("schema"))
