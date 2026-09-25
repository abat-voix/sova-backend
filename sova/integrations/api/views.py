import json
import secrets
import uuid

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.decorators import action

from sova.integrations.api.permissions import CanManageIntegrations
from sova.integrations.api.serializers import (
    IntegrationMappingPreviewSerializer,
    IntegrationMappingSerializer,
    IntegrationEntityMetadataSerializer,
    IntegrationMessageResponseSerializer,
    IntegrationSystemSerializer,
)
from sova.integrations.mapping import preview_mapping
from sova.integrations.models import IntegrationMapping
from sova.integrations.registry import ENTITIES
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


def _field_type(field):
    if isinstance(field, serializers.ManyRelatedField) or getattr(field, "many", False):
        return "array"
    for field_class, name in (
        (serializers.ChoiceField, "choice"),
        (serializers.UUIDField, "uuid"),
        (serializers.DateTimeField, "datetime"),
        (serializers.DateField, "date"),
        (serializers.BooleanField, "boolean"),
        (serializers.IntegerField, "integer"),
        (serializers.FloatField, "number"),
        (serializers.DecimalField, "number"),
        (serializers.JSONField, "json"),
        (serializers.RelatedField, "relation"),
        (serializers.ListField, "array"),
        (serializers.DictField, "object"),
    ):
        if isinstance(field, field_class):
            return name
    return "string"


def _field_metadata(name, field):
    raw_choices = getattr(field, "choices", {})
    choices = [
        {"value": value, "label": str(label)}
        for value, label in raw_choices.items()
        if isinstance(value, (str, int, bool))
    ]
    return {
        "name": name,
        "label": str(field.label or name),
        "help_text": str(field.help_text or ""),
        "type": _field_type(field),
        "required": field.required,
        "read_only": field.read_only,
        "allow_null": field.allow_null,
        "many": bool(getattr(field, "many", False) or isinstance(field, serializers.ManyRelatedField)),
        "choices": choices,
    }


class IntegrationEntityMetadataView(APIView):
    permission_classes = (CanManageIntegrations,)

    @extend_schema(tags=["integrations"], responses=IntegrationEntityMetadataSerializer(many=True))
    def get(self, request):
        return Response([
            {
                "code": entity.code,
                "label": entity.label,
                "serializer": f"{entity.serializer.__module__}.{entity.serializer.__name__}",
                "fields": [_field_metadata(name, field) for name, field in entity.serializer().fields.items()],
            }
            for entity in ENTITIES.values()
        ])


class IntegrationSystemsView(APIView):
    permission_classes = (CanManageIntegrations,)

    @extend_schema(tags=["integrations"], responses=IntegrationSystemSerializer(many=True))
    def get(self, request):
        labels = {"lms": "LMS", "cms": "CMS"}
        return Response([
            {"code": code, "label": config.get("label", labels.get(code, code.upper()))}
            for code, config in settings.INTEGRATION_SYSTEMS.items()
        ])


class IntegrationMappingViewSet(ModelViewSet):
    queryset = IntegrationMapping.objects.all()
    serializer_class = IntegrationMappingSerializer
    permission_classes = (CanManageIntegrations,)
    pagination_class = None
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    @action(detail=False, methods=("post",), url_path="preview")
    def preview(self, request):
        serializer = IntegrationMappingPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(preview_mapping(**serializer.validated_data))
