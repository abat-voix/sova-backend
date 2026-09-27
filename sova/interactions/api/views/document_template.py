from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from sova.interactions.api.serializers.document_template import DocumentTemplateFieldsSerializer
from sova.interactions.enum import DocumentTemplateKind
from sova.interactions.services.document_template_fields import contract_template_fields


class DocumentTemplateFieldsView(APIView):
    """Все поля, которые можно использовать в DOCX-шаблоне выбранного типа."""

    @extend_schema(
        parameters=[OpenApiParameter("kind", str, description="Тип шаблона. Пока поддерживается только contract.")],
        responses=DocumentTemplateFieldsSerializer,
    )
    def get(self, request) -> Response:
        kind = request.query_params.get("kind", DocumentTemplateKind.CONTRACT)
        if kind != DocumentTemplateKind.CONTRACT:
            raise ValidationError({"kind": ["Поддерживается только тип contract."]})
        return Response(contract_template_fields())
