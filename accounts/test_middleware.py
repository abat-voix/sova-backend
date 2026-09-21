from urllib.parse import parse_qs, urlparse

from django.contrib.auth import BACKEND_SESSION_KEY
from django.test import TestCase

from sova.core.tests.factories import UserFactory


class ApiSessionRefreshTests(TestCase):
    """Поведение продления сессии OIDC для API и для навигации браузера."""

    def setUp(self) -> None:
        """Входит пользователем OIDC с заведомо истёкшим id token."""
        self.user = UserFactory()
        self.client.force_login(
            self.user,
            backend="accounts.auth.KeycloakOIDCAuthenticationBackend",
        )
        self.expire_id_token()

    def expire_id_token(self) -> None:
        """Помечает id token истёкшим, сохраняя признак входа через OIDC."""
        session = self.client.session
        session[BACKEND_SESSION_KEY] = (
            "accounts.auth.KeycloakOIDCAuthenticationBackend"
        )
        session["oidc_id_token_expiration"] = 1.0
        session.save()

    def test_api_request_gets_json_401_instead_of_redirect(self) -> None:
        """Запрос к API получает JSON с кодом `session_expired`, а не редирект."""
        response = self.client.get("/api/users/", headers={"accept": "application/json"})

        # Проверяем статус и машиночитаемый код
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["code"], "session_expired")

    def test_api_response_carries_refresh_and_login_urls(self) -> None:
        """В ответе есть адрес молчаливого продления и адрес полного входа."""
        response = self.client.get("/api/users/", headers={"accept": "application/json"})

        payload = response.json()
        refresh_url = urlparse(payload["refresh_url"])
        # Проверяем, что продление ведёт на Keycloak в режиме prompt=none
        self.assertEqual(refresh_url.path, "/realms/sova/protocol/openid-connect/auth")
        self.assertEqual(parse_qs(refresh_url.query)["prompt"], ["none"])
        # Проверяем адрес полноценного входа
        self.assertEqual(payload["login_url"], "/api/auth/oidc/authenticate/")

    def test_api_request_does_not_leave_api_path_as_return_url(self) -> None:
        """После API-запроса возврат со входа не ведёт на JSON-ответ."""
        self.client.get("/api/users/?page=1", headers={"accept": "application/json"})

        # Проверяем, что путь API не сохранён как «куда вернуться»
        self.assertIsNone(self.client.session.get("oidc_login_next"))

    def test_xhr_request_gets_the_same_json_401(self) -> None:
        """Ответ одинаков и для клиентов, присылающих X-Requested-With."""
        response = self.client.get(
            "/api/users/",
            headers={"x-requested-with": "XMLHttpRequest"},
        )

        # Проверяем единый формат ответа
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "session_expired")

    def test_browser_navigation_still_gets_redirect(self) -> None:
        """Навигация браузера по API-пути получает прежний редирект на Keycloak."""
        response = self.client.get(
            "/api/docs/",
            headers={"accept": "text/html,application/xhtml+xml"},
        )

        # Проверяем, что поведение для Swagger UI не изменилось
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response["Location"]).path,
            "/realms/sova/protocol/openid-connect/auth",
        )

    def test_non_api_path_still_gets_redirect(self) -> None:
        """Пути вне `/api/` продлевают сессию редиректом, как раньше."""
        response = self.client.get("/admin/")

        # Проверяем, что Django Admin работает по-прежнему
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response["Location"]).path,
            "/realms/sova/protocol/openid-connect/auth",
        )

    def test_valid_id_token_passes_through(self) -> None:
        """Пока id token не истёк, middleware в запрос не вмешивается."""
        session = self.client.session
        session["oidc_id_token_expiration"] = 2**31
        session.save()

        response = self.client.get("/api/auth/me/", headers={"accept": "application/json"})

        # Проверяем обычный ответ приложения
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])

    def test_exempt_url_is_not_intercepted(self) -> None:
        """Освобождённый `/api/auth/me/` отвечает и при истёкшем id token."""
        response = self.client.get("/api/auth/me/", headers={"accept": "application/json"})

        # Проверяем, что список исключений соблюдается
        self.assertEqual(response.status_code, 200)

    def test_session_login_backend_without_oidc_is_untouched(self) -> None:
        """Сессии локального Django-входа продление OIDC не касается."""
        session = self.client.session
        session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
        session.save()

        response = self.client.get("/api/users/", headers={"accept": "application/json"})

        # Проверяем, что ответ формирует приложение, а не middleware
        self.assertNotEqual(response.status_code, 401)
