from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE


health_response = inline_serializer(
    name="HealthResponse",
    fields={
        "status": serializers.CharField(),
        "database": serializers.CharField(),
        "cache": serializers.CharField(),
    },
)


@extend_schema(
    summary="Проверить состояние сервиса",
    description="Проверяет доступность базы данных и cache/Redis.",
    responses={200: health_response, 503: health_response},
)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([])
def health(request):
    checks = {"status": "ok", "database": "ok", "cache": "ok"}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        checks["status"] = "error"
        checks["database"] = "error"

    try:
        cache.set("sova-healthcheck", "ok", timeout=5)
        if cache.get("sova-healthcheck") != "ok":
            raise RuntimeError("Cache healthcheck value could not be read back.")
    except Exception:
        checks["status"] = "error"
        checks["cache"] = "error"

    status_code = HTTP_200_OK if checks["status"] == "ok" else HTTP_503_SERVICE_UNAVAILABLE
    return Response(checks, status=status_code)
