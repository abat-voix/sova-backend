import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

# Loads .env for local runs. Existing environment variables win, so values
# injected by Docker Compose are never overridden.
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()
DEBUG = env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if ENVIRONMENT in {"development", "test", "testing"}:
        SECRET_KEY = "unsafe-development-key-do-not-use-in-production"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set outside development.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "mozilla_django_oidc",
    "accounts",
    "health",
    "sova.catalog",
    "sova.interactions",
    "sova.workflows",
    "sova.processes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.ApiSessionRefresh",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "sova.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "sova.wsgi.application"
ASGI_APPLICATION = "sova.asgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

REDIS_URL = os.getenv("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "sova-local-cache",
        }
    }

GOTENBERG_URL = os.getenv("GOTENBERG_URL", "http://localhost:3001").rstrip("/")
try:
    GOTENBERG_TIMEOUT = float(os.getenv("GOTENBERG_TIMEOUT", "30"))
except ValueError as error:
    raise ImproperlyConfigured("GOTENBERG_TIMEOUT must be a number.") from error

if GOTENBERG_TIMEOUT <= 0:
    raise ImproperlyConfigured("GOTENBERG_TIMEOUT must be greater than zero.")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles"))
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))

EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", default=True)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    "СОВА <noreply@1uup.ru>",
)

smtp_settings = {
    "EMAIL_HOST": EMAIL_HOST,
    "EMAIL_HOST_USER": EMAIL_HOST_USER,
    "EMAIL_HOST_PASSWORD": EMAIL_HOST_PASSWORD,
}
missing_smtp_settings = [name for name, value in smtp_settings.items() if not value]

if missing_smtp_settings:
    if len(missing_smtp_settings) != len(smtp_settings):
        raise ImproperlyConfigured(
            f"Incomplete SMTP configuration; missing: {', '.join(missing_smtp_settings)}."
        )
    if ENVIRONMENT not in {"development", "test", "testing"}:
        raise ImproperlyConfigured(
            "EMAIL_HOST, EMAIL_HOST_USER and EMAIL_HOST_PASSWORD must be set "
            "outside development."
        )
    EMAIL_BACKEND = (
        "django.core.mail.backends.locmem.EmailBackend"
        if ENVIRONMENT in {"test", "testing"}
        else "django.core.mail.backends.console.EmailBackend"
    )
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTHENTICATION_BACKENDS = [
    "accounts.auth.KeycloakOIDCAuthenticationBackend",
    "django.contrib.auth.backends.ModelBackend",
]

APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip("/")
KEYCLOAK_PUBLIC_URL = os.getenv(
    "KEYCLOAK_PUBLIC_URL", "http://localhost:8080"
).rstrip("/")
KEYCLOAK_INTERNAL_URL = os.getenv(
    "KEYCLOAK_INTERNAL_URL", KEYCLOAK_PUBLIC_URL
).rstrip("/")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "sova")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "sova-web")
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "")

if not KEYCLOAK_CLIENT_SECRET and ENVIRONMENT not in {
    "development",
    "test",
    "testing",
}:
    raise ImproperlyConfigured(
        "KEYCLOAK_CLIENT_SECRET must be set outside development."
    )

KEYCLOAK_PUBLIC_REALM_URL = f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}"
KEYCLOAK_INTERNAL_REALM_URL = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}"

OIDC_RP_CLIENT_ID = KEYCLOAK_CLIENT_ID
OIDC_RP_CLIENT_SECRET = KEYCLOAK_CLIENT_SECRET
OIDC_RP_SCOPES = "openid profile email"
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_OP_AUTHORIZATION_ENDPOINT = (
    f"{KEYCLOAK_PUBLIC_REALM_URL}/protocol/openid-connect/auth"
)
OIDC_OP_TOKEN_ENDPOINT = (
    f"{KEYCLOAK_INTERNAL_REALM_URL}/protocol/openid-connect/token"
)
OIDC_OP_USER_ENDPOINT = (
    f"{KEYCLOAK_INTERNAL_REALM_URL}/protocol/openid-connect/userinfo"
)
OIDC_OP_JWKS_ENDPOINT = (
    f"{KEYCLOAK_INTERNAL_REALM_URL}/protocol/openid-connect/certs"
)
OIDC_USE_PKCE = True
OIDC_PKCE_CODE_CHALLENGE_METHOD = "S256"
OIDC_VERIFY_JWT = True
OIDC_VERIFY_KID = True
OIDC_USE_NONCE = True
OIDC_VERIFY_SSL = True
OIDC_TIMEOUT = 10
OIDC_STORE_ACCESS_TOKEN = False
OIDC_STORE_ID_TOKEN = True
OIDC_OP_LOGOUT_URL_METHOD = "accounts.oidc.provider_logout_url"
OIDC_REDIRECT_ALLOWED_HOSTS = ALLOWED_HOSTS
OIDC_EXEMPT_URLS = ["/api/health/", "/api/auth/me/"]
OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = 15 * 60

LOGIN_REDIRECT_URL = APP_PUBLIC_URL
LOGIN_REDIRECT_URL_FAILURE = APP_PUBLIC_URL
LOGOUT_REDIRECT_URL = APP_PUBLIC_URL

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        # Формы и фильтры в браузере — только при разработке
        *(["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication"
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "sova.core.api.schema.SovaAutoSchema",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "sova.core.api.pagination.StandardPagination",
    "EXCEPTION_HANDLER": "sova.core.api.exceptions.exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SOVA API",
    "DESCRIPTION": "API backend проекта СОВА.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_AUTHENTICATION": [],
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    # Явные имена перечислений: у нескольких моделей есть поля с одинаковыми названиями (status, type)
    "ENUM_NAME_OVERRIDES": {
        "WorkflowInstanceStatusEnum": "sova.processes.enum.WorkflowInstanceStatus",
        "StageInstanceStatusEnum": "sova.processes.enum.StageInstanceStatus",
        "ActionInstanceStatusEnum": "sova.processes.enum.ActionInstanceStatus",
        "StageInstanceContextTypeEnum": "sova.processes.enum.StageInstanceContextType",
    },
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "sova_sessionid"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", str(8 * 60 * 60)))
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "SAMEORIGIN"
