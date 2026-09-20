from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.auth import KeycloakOIDCAuthenticationBackend
from accounts.models import SystemRole, UserRole
from accounts.oidc import provider_logout_url


class KeycloakOIDCAuthenticationBackendTests(TestCase):
    def setUp(self) -> None:
        self.backend = KeycloakOIDCAuthenticationBackend()
        self.claims = {
            "sub": "3f21d5ea-59d8-4b41-b15d-18dddc4dc093",
            "email": "owl@example.com",
            "given_name": "Сова",
            "family_name": "Совова",
        }

    def test_creates_user_with_keycloak_subject_and_no_password(self) -> None:
        user = self.backend.create_user(self.claims)

        self.assertEqual(user.username, self.claims["sub"])
        self.assertEqual(user.email, "owl@example.com")
        self.assertEqual(user.get_full_name(), "Сова Совова")
        self.assertFalse(user.has_usable_password())

    def test_finds_and_updates_user_by_subject_not_email(self) -> None:
        user = self.backend.create_user(self.claims)
        changed_claims = {**self.claims, "email": "new@example.com"}

        found = self.backend.filter_users_by_claims(changed_claims).get()
        updated = self.backend.update_user(found, changed_claims)

        self.assertEqual(updated.pk, user.pk)
        self.assertEqual(updated.email, "new@example.com")

    def test_rejects_claims_without_subject(self) -> None:
        self.assertFalse(self.backend.verify_claims({"email": "owl@example.com"}))


class SessionViewTests(TestCase):
    def test_anonymous_session_response_sets_csrf_cookie(self) -> None:
        response = self.client.get(reverse("accounts:session"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["authenticated"])
        self.assertIn("csrfToken", response.json())
        self.assertIn("csrftoken", response.cookies)

    def test_authenticated_session_returns_user(self) -> None:
        user = get_user_model().objects.create_user(
            username="keycloak-subject",
            email="owl@example.com",
            first_name="Сова",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:session"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])
        self.assertEqual(response.json()["user"]["displayName"], "Сова")
        self.assertIsNone(response.json()["user"]["role"])
        self.assertIsNone(response.json()["user"]["roleDisplay"])
        self.assertEqual(response.json()["user"]["roles"], [])

    def test_authenticated_session_returns_selected_system_role(self) -> None:
        user = get_user_model().objects.create_user(username="kam-subject")
        UserRole.objects.create(user=user, role=SystemRole.KAM)
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:session"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "kam")
        self.assertEqual(response.json()["user"]["roleDisplay"], "КАМ")
        self.assertEqual(response.json()["user"]["roles"], ["kam"])


class UserRoleTests(TestCase):
    def test_user_can_have_only_one_system_role(self) -> None:
        user = get_user_model().objects.create_user(username="role-subject")

        UserRole.objects.create(user=user, role=SystemRole.HEAD)

        self.assertEqual(user.system_role.role, SystemRole.HEAD)

    def test_system_role_does_not_make_user_django_superuser(self) -> None:
        user = get_user_model().objects.create_user(username="admin-subject")
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)

        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)


class OIDCFlowTests(TestCase):
    @override_settings(
        OIDC_OP_AUTHORIZATION_ENDPOINT=(
            "https://auth.dev.sova.1uup.ru/realms/sova/protocol/openid-connect/auth"
        ),
        OIDC_RP_CLIENT_ID="sova-web",
        OIDC_USE_PKCE=True,
        OIDC_PKCE_CODE_CHALLENGE_METHOD="S256",
    )
    def test_login_redirect_uses_code_flow_with_pkce(self) -> None:
        response = self.client.get(
            reverse("oidc_authentication_init"), {"next": "/"}
        )

        self.assertEqual(response.status_code, 302)
        location = urlparse(response.url)
        query = parse_qs(location.query)
        self.assertEqual(location.netloc, "auth.dev.sova.1uup.ru")
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["sova-web"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(
            query["redirect_uri"],
            ["http://testserver/api/auth/oidc/callback/"],
        )


class ProviderLogoutUrlTests(TestCase):
    @override_settings(
        APP_PUBLIC_URL="https://dev.sova.1uup.ru",
        KEYCLOAK_PUBLIC_REALM_URL="https://auth.dev.sova.1uup.ru/realms/sova",
        KEYCLOAK_CLIENT_ID="sova-web",
    )
    def test_includes_id_token_hint_when_available(self) -> None:
        request = RequestFactory().post("/api/auth/oidc/logout/")
        request.user = AnonymousUser()
        request.session = {"oidc_id_token": "signed-token"}

        result = provider_logout_url(request)

        self.assertIn("id_token_hint=signed-token", result)
        self.assertIn(
            "post_logout_redirect_uri=https%3A%2F%2Fdev.sova.1uup.ru%2F", result
        )

    @override_settings(
        APP_PUBLIC_URL="https://dev.sova.1uup.ru",
        KEYCLOAK_PUBLIC_REALM_URL="https://auth.dev.sova.1uup.ru/realms/sova",
        KEYCLOAK_CLIENT_ID="sova-web",
    )
    def test_falls_back_to_client_id_without_id_token(self) -> None:
        request = SimpleNamespace(session={})

        result = provider_logout_url(request)

        self.assertIn("client_id=sova-web", result)
