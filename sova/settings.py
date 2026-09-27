import os
import sys
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from sova.core.storage import s3_storage


BASE_DIR = Path(__file__).resolve().parent.parent

# Loads .env for local runs. Existing environment variables win, so values
# injected by Docker Compose are never overridden.
load_dotenv(BASE_DIR / ".env")

# `manage.py test ...` — тесты всегда работают с файловой системой (временный MEDIA_ROOT из
# TemporaryMediaMixin), независимо от STORAGE_BACKEND в окружении разработчика или CI.
TESTING = "test" in sys.argv


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
    "daphne",
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
    "sova.core",
    "sova.catalog",
    "sova.interactions",
    "sova.workflows",
    "sova.processes",
    "sova.notifications",
    "sova.messaging",
    "sova.realtime",
    "sova.reports",
    "sova.integrations",
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

try:
    REALTIME_MAX_CONNECTION_AGE_SECONDS = int(
        os.getenv("REALTIME_MAX_CONNECTION_AGE_SECONDS", "1800")
    )
except ValueError as error:
    raise ImproperlyConfigured(
        "REALTIME_MAX_CONNECTION_AGE_SECONDS must be an integer."
    ) from error
if REALTIME_MAX_CONNECTION_AGE_SECONDS <= 0:
    raise ImproperlyConfigured(
        "REALTIME_MAX_CONNECTION_AGE_SECONDS must be greater than zero."
    )

try:
    REALTIME_CHANNEL_CAPACITY = int(os.getenv("REALTIME_CHANNEL_CAPACITY", "100"))
except ValueError as error:
    raise ImproperlyConfigured("REALTIME_CHANNEL_CAPACITY must be an integer.") from error
if REALTIME_CHANNEL_CAPACITY <= 0:
    raise ImproperlyConfigured("REALTIME_CHANNEL_CAPACITY must be greater than zero.")

CHANNEL_REDIS_URL = os.getenv("CHANNEL_REDIS_URL", "").strip()
CHANNEL_REDIS_URL_MISSING = not CHANNEL_REDIS_URL
if TESTING or ENVIRONMENT in {"test", "testing"}:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }
else:
    if not CHANNEL_REDIS_URL:
        CHANNEL_REDIS_URL = "redis://localhost:6379/2"
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                # channels_redis waits up to 5 seconds in its blocking receive.
                # Keep redis-py's socket read timeout above that interval; its
                # default timeout of 5 seconds can otherwise disconnect idle
                # WebSockets before the Redis command returns normally.
                "hosts": [{"address": CHANNEL_REDIS_URL, "socket_timeout": 10}],
                "prefix": "sova-realtime",
                "expiry": 60,
                "group_expiry": REALTIME_MAX_CONNECTION_AGE_SECONDS + 60,
                "capacity": REALTIME_CHANNEL_CAPACITY,
            },
        },
    }

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

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "") or None
CELERY_TASK_IGNORE_RESULT = True
# Без брокера (локальная разработка, тесты) задания выполняются синхронно в процессе API
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", default=not CELERY_BROKER_URL)
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ROUTES = {
    "sova.integrations.tasks.*": {"queue": "integrations"},
}
# На macOS prefork запускает дочерние процессы через spawn: в Celery 5.6
# fast_trace_task остаётся без инициализированного реестра задач. Для локального
# worker используем однопроцессный пул; Linux в контейнере сохраняет prefork.
if sys.platform == "darwin" and ENVIRONMENT == "development":
    CELERY_WORKER_POOL = os.getenv("CELERY_WORKER_POOL", "solo")
CELERY_TIMEZONE = "Europe/Moscow"
# Час ежедневной рассылки уведомлений о сроках (по CELERY_TIMEZONE)
OVERDUE_NOTIFY_HOUR = int(os.getenv("OVERDUE_NOTIFY_HOUR", "9"))
# Срок хранения уведомлений в системе, дней (прочитанных и непрочитанных)
NOTIFICATIONS_RETENTION_DAYS = int(os.getenv("NOTIFICATIONS_RETENTION_DAYS", "60"))
CELERY_BEAT_SCHEDULE = {
    "dispatch-integration-messages": {
        "task": "sova.integrations.tasks.dispatch_pending_integration_messages",
        "schedule": 60,
    },
    "cleanup-report-jobs": {
        "task": "sova.reports.tasks.cleanup_report_jobs",
        "schedule": 60 * 60,
    },
    "cleanup-staged-message-attachments": {
        "task": "sova.messaging.tasks.cleanup_staged_message_attachments",
        "schedule": 60 * 60,
    },
    "notify-deadlines": {
        "task": "sova.processes.tasks.notify_deadlines",
        "schedule": crontab(hour=OVERDUE_NOTIFY_HOUR, minute=0),
    },
    "cleanup-notifications": {
        "task": "sova.notifications.tasks.cleanup_notifications",
        "schedule": crontab(hour=3, minute=0),
    },
}

INTEGRATION_SYSTEMS = {
    "lms": {
        "url": os.getenv("INTEGRATION_LMS_URL", "").strip(),
        "inbound_token": os.getenv("INTEGRATION_LMS_INBOUND_TOKEN", ""),
        "outbound_token": os.getenv("INTEGRATION_LMS_OUTBOUND_TOKEN", ""),
    },
    "cms": {
        "url": os.getenv("INTEGRATION_CMS_URL", "").strip(),
        "inbound_token": os.getenv("INTEGRATION_CMS_INBOUND_TOKEN", ""),
        "outbound_token": os.getenv("INTEGRATION_CMS_OUTBOUND_TOKEN", ""),
    },
}
INTEGRATION_HTTP_TIMEOUT = float(os.getenv("INTEGRATION_HTTP_TIMEOUT", "10"))
INTEGRATION_MAX_ATTEMPTS = int(os.getenv("INTEGRATION_MAX_ATTEMPTS", "5"))
INTEGRATION_MAX_PAYLOAD_BYTES = int(os.getenv("INTEGRATION_MAX_PAYLOAD_BYTES", str(1024 * 1024)))
if ENVIRONMENT in {"production", "prod"}:
    for _system_name, _system_config in INTEGRATION_SYSTEMS.items():
        if _system_config["url"] and not _system_config["inbound_token"]:
            raise ImproperlyConfigured(
                f"INTEGRATION_{_system_name.upper()}_INBOUND_TOKEN must be set when the integration is enabled."
            )

# Приватное хранилище файлов отчётов: вне MEDIA_ROOT, отдаётся только через API.
# API и worker должны видеть один и тот же каталог (общий том) или общий backend.
REPORTS_STORAGE_ROOT = Path(os.getenv("REPORTS_STORAGE_ROOT", BASE_DIR / "private" / "reports"))
REPORTS_RETENTION_HOURS = int(os.getenv("REPORTS_RETENTION_HOURS", "72"))
REPORTS_JOB_TIMEOUT_SECONDS = int(os.getenv("REPORTS_JOB_TIMEOUT_SECONDS", str(30 * 60)))
REPORTS_MAX_ATTEMPTS = int(os.getenv("REPORTS_MAX_ATTEMPTS", "3"))
REPORTS_MAX_PERIOD_DAYS = int(os.getenv("REPORTS_MAX_PERIOD_DAYS", str(5 * 366)))
REPORTS_MAX_FILTER_ITEMS = int(os.getenv("REPORTS_MAX_FILTER_ITEMS", "500"))
REPORTS_MAX_ACTIVE_JOBS_PER_USER = int(os.getenv("REPORTS_MAX_ACTIVE_JOBS_PER_USER", "5"))
REPORTS_PREVIEW_MAX_PAGE_SIZE = 200
REPORTS_PDF_MAX_ROWS = int(os.getenv("REPORTS_PDF_MAX_ROWS", "5000"))
REPORTS_XLS_MAX_SHEETS = int(os.getenv("REPORTS_XLS_MAX_SHEETS", "4"))

# Хранилище файлов: `filesystem` (по умолчанию, тесты и локальный запуск без Docker) или `s3`
# (собственный Garage или внешний S3-совместимый провайдер — см. docs/plans/2026-09-23-s3-storage.md).
# Переключение — только переменными окружения, код хранилища не знает, с каким провайдером
# работает.
STORAGE_BACKEND = "filesystem" if TESTING else os.getenv("STORAGE_BACKEND", "filesystem")
# Как отдавать файл авторизованному пользователю: `proxy` — Django стримит его сам (хранилище
# остаётся только во внутренней сети), `redirect` — 302 на подписанный URL (для провайдера,
# чей endpoint виден браузеру).
S3_DOWNLOAD_MODE = os.getenv("S3_DOWNLOAD_MODE", "proxy")
FILE_UPLOAD_MAX_SIZE = int(os.getenv("FILE_UPLOAD_MAX_SIZE_MB", "25")) * 1024 * 1024
MESSAGE_ATTACHMENT_STAGING_TTL_HOURS = int(os.getenv("MESSAGE_ATTACHMENT_STAGING_TTL_HOURS", "24"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "reports": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": REPORTS_STORAGE_ROOT, "base_url": None},
    },
}

if STORAGE_BACKEND == "s3":
    try:
        S3_MEDIA_BUCKET = os.environ["S3_MEDIA_BUCKET"]
        S3_REPORTS_BUCKET = os.environ["S3_REPORTS_BUCKET"]
    except KeyError as exc:
        raise ImproperlyConfigured(
            "STORAGE_BACKEND=s3 требует S3_MEDIA_BUCKET и S3_REPORTS_BUCKET."
        ) from exc
    STORAGES["default"] = s3_storage(S3_MEDIA_BUCKET)
    STORAGES["reports"] = s3_storage(S3_REPORTS_BUCKET, location="reports")
elif STORAGE_BACKEND != "filesystem":
    raise ImproperlyConfigured(
        f"Неизвестный STORAGE_BACKEND={STORAGE_BACKEND!r}, допустимо: filesystem, s3."
    )

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

if CHANNEL_REDIS_URL_MISSING and ENVIRONMENT not in {"development", "test", "testing"}:
    raise ImproperlyConfigured("CHANNEL_REDIS_URL must be set outside development.")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "")
TELEGRAM_PROXY = os.getenv("TELEGRAM_PROXY", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_LINK_TOKEN_TTL_MINUTES = int(os.getenv("TELEGRAM_LINK_TOKEN_TTL_MINUTES", "30"))
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
MAX_API_URL = os.getenv("MAX_API_URL", "https://platform-api.max.ru").rstrip("/")
NOTIFICATION_HTTP_TIMEOUT = float(os.getenv("NOTIFICATION_HTTP_TIMEOUT", "10"))

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
OIDC_CALLBACK_CLASS = "accounts.oidc.SovaOIDCAuthenticationCallbackView"
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
    "DEFAULT_PERMISSION_CLASSES": ["accounts.api.permissions.PolicyPermission"],
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
        "KindEnum": "sova.catalog.enum.ClientKind",
        "NotificationKindEnum": "sova.notifications.enum.NotificationKind",
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
