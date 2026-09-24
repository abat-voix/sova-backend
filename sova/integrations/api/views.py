import json
import secrets
import uuid

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from sova.integrations.api.serializers import IntegrationMessageResponseSerializer
from sova.integrations.services import receive_message


def _error(code, message, http_status):
    return Response({"detail": message, "code": code}, status=http_status)


@method_decorator(csrf_exempt, name="dispatch")
class IntegrationEventsView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["integrations"],
        request=OpenApiTypes.OBJECT,
        responses={202: IntegrationMessageResponseSerializer, 200: IntegrationMessageResponseSerializer},
        parameters=[
            OpenApiParameter("Authorization", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True),
            OpenApiParameter("X-Event-Id", OpenApiTypes.STR, OpenApiParameter.HEADER),
            OpenApiParameter("X-Event-Type", OpenApiTypes.STR, OpenApiParameter.HEADER),
            OpenApiParameter("X-Correlation-Id", OpenApiTypes.UUID, OpenApiParameter.HEADER),
        ],
    )
    def post(self, request, system_code):
        config = settings.INTEGRATION_SYSTEMS.get(system_code)
        if config is None:
            return _error("unknown_integration_system", "Unknown integration system", status.HTTP_404_NOT_FOUND)
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        expected = config.get("inbound_token", "")
        if scheme.lower() != "bearer" or not expected or not secrets.compare_digest(token, expected):
            return _error("invalid_integration_token", "Invalid integration token", status.HTTP_401_UNAUTHORIZED)
        if len(request.body) > settings.INTEGRATION_MAX_PAYLOAD_BYTES:
            return _error("payload_too_large", "Payload is too large", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _error("invalid_json", "Request body must be valid JSON", status.HTTP_400_BAD_REQUEST)
        if not isinstance(payload, dict):
            return _error("invalid_json", "Request body must be a JSON object", status.HTTP_400_BAD_REQUEST)

        external_id = request.headers.get("X-Event-Id") or payload.get("eventId", "")
        event_type = request.headers.get("X-Event-Type") or payload.get("eventType", "") or "generic.received"
        correlation_raw = request.headers.get("X-Correlation-Id") or payload.get("correlationId")
        try:
            correlation_id = uuid.UUID(correlation_raw) if correlation_raw else None
        except (ValueError, AttributeError, TypeError):
            return _error("invalid_correlation_id", "Correlation ID must be a UUID", status.HTTP_400_BAD_REQUEST)
        try:
            result = receive_message(
                system=system_code,
                event_type=str(event_type),
                payload=payload,
                external_id=str(external_id or ""),
                correlation_id=correlation_id,
            )
        except ValueError as exc:
            return _error("invalid_payload", str(exc), status.HTTP_400_BAD_REQUEST)
        response = {"id": result.message.pk, "status": result.message.status, "duplicate": result.duplicate}
        return Response(response, status=status.HTTP_200_OK if result.duplicate else status.HTTP_202_ACCEPTED)
