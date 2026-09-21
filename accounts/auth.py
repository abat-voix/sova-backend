from typing import Any

from django.contrib.auth import get_user_model
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class KeycloakOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Map a Keycloak identity to a local Django user by its stable subject."""

    def filter_users_by_claims(self, claims: dict[str, Any]):
        subject = claims.get("sub")
        if not subject:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(username=subject)

    def verify_claims(self, claims: dict[str, Any]) -> bool:
        return bool(claims.get("sub")) and super().verify_claims(claims)

    def create_user(self, claims: dict[str, Any]):
        user_model = get_user_model()
        user = user_model(username=claims["sub"])
        user.set_unusable_password()
        self._apply_claims(user, claims)
        user.save()
        return user

    def update_user(self, user, claims: dict[str, Any]):
        self._apply_claims(user, claims)
        user.save(update_fields=["email", "first_name", "last_name"])
        return user

    @staticmethod
    def _apply_claims(user, claims: dict[str, Any]) -> None:
        user.email = claims.get("email", "")
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
