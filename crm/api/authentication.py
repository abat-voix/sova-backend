import jwt
from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from crm.services.keycloak_sync import sync_user_from_claims

_jwks_client: jwt.PyJWKClient | None = None


def get_jwks_client() -> jwt.PyJWKClient:
    """Ленивый синглтон клиента JWKS Keycloak (кэширует публичные ключи сам)."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(settings.KEYCLOAK_JWKS_URL, cache_keys=True)
    return _jwks_client


class KeycloakAuthentication(BaseAuthentication):
    """
    Проверяет Bearer JWT, выданный Keycloak, и синхронизирует пользователя/роли.

    Подпись токена сверяется с публичным ключом, полученным из JWKS-эндпоинта
    реалма Keycloak (settings.KEYCLOAK_JWKS_URL), затем проверяются issuer и
    audience. При успехе — get-or-create пользователя и синхронизация ролей
    (см. crm.services.keycloak_sync.sync_user_from_claims).
    """

    keyword = "Bearer"

    def authenticate(self, request):
        """Возвращает (user, token) при валидном токене, None — если заголовка нет вовсе."""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith(f"{self.keyword} "):
            return None

        token = auth_header[len(self.keyword) + 1 :]
        claims = self._decode(token)
        user = sync_user_from_claims(claims)
        return (user, token)

    def authenticate_header(self, request) -> str:
        """Значение WWW-Authenticate в ответе 401."""
        return self.keyword

    def _decode(self, token: str) -> dict:
        """Проверяет подпись/issuer/audience токена, возвращает claims."""
        try:
            signing_key = get_jwks_client().get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.KEYCLOAK_AUDIENCE,
                issuer=settings.KEYCLOAK_ISSUER,
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationFailed(f"Невалидный Keycloak-токен: {exc}") from exc


class KeycloakAuthenticationScheme(OpenApiAuthenticationExtension):
    """Описывает KeycloakAuthentication для Swagger UI как Bearer JWT."""

    target_class = KeycloakAuthentication
    name = "KeycloakAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
