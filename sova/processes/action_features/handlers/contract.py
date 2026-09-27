from rest_framework import serializers

from sova.interactions.enum import DocumentTemplateKind
from sova.interactions.models import (
    Contract,
    DocumentTemplate,
    InteractionContact,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    License,
)
from sova.interactions.services.contract_files import record_contract_file
from sova.interactions.services.document_templates import (
    DocumentTemplateRenderError,
    render_contract_template,
)
from sova.processes.action_features.base import ActionFeatureResult
from sova.processes.action_features.errors import ActionFeatureError


class ContractCounterpartySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=500)
    short_name = serializers.CharField(max_length=255, allow_blank=True, default="")
    inn = serializers.CharField(max_length=12, allow_blank=True, default="")
    address = serializers.CharField(max_length=1000, allow_blank=True, default="")
    email = serializers.EmailField(allow_blank=True, default="")
    phone = serializers.CharField(max_length=50, allow_blank=True, default="")


class ContractSignatorySerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255, allow_blank=True, default="")
    position = serializers.CharField(max_length=255, allow_blank=True, default="")
    basis = serializers.CharField(max_length=255, allow_blank=True, default="")


class ContractDocumentSerializer(serializers.Serializer):
    """Данные договора — контекст рендера шаблона docxtpl (`{{ counterparty.name }}` и т. п.)."""

    contract_number = serializers.CharField(max_length=255, allow_blank=True, default="")
    contract_date = serializers.DateField(allow_null=True, default=None)
    city = serializers.CharField(max_length=255, allow_blank=True, default="")
    counterparty = ContractCounterpartySerializer()
    signatory = ContractSignatorySerializer(default=dict)
    # Состав взаимодействия: фронтенд присылает выбранные элементы, бэкенд по `id`
    # перезаполняет их из БД (см. `_resolve_scope`) — в шаблон попадают только данные взаимодействия.
    directions = serializers.ListField(child=serializers.DictField(), default=list)
    programs = serializers.ListField(child=serializers.DictField(), default=list)
    products = serializers.ListField(child=serializers.DictField(), default=list)
    licenses = serializers.ListField(child=serializers.DictField(), default=list)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, default=None)
    comment = serializers.CharField(allow_blank=True, default="")


class CreateContractPayloadSerializer(serializers.Serializer):
    template = serializers.PrimaryKeyRelatedField(
        queryset=DocumentTemplate.objects.filter(kind=DocumentTemplateKind.CONTRACT, is_active=True),
    )
    document = ContractDocumentSerializer()


def _contract_templates():
    return (
        DocumentTemplate.objects.filter(kind=DocumentTemplateKind.CONTRACT, is_active=True)
        .exclude(file="")
        .exclude(file__isnull=True)
    )


def _counterparty(context) -> dict:
    if context.university:
        university = context.university
        return {
            "name": university.name,
            "short_name": university.short_name,
            "inn": university.inn or "",
            "address": "",
            "email": university.email,
            "phone": university.phone,
        }
    client = context.b2c_client
    return {
        "name": client.full_name,
        "short_name": "",
        "inn": client.inn or "",
        "address": "",
        "email": client.email,
        "phone": client.phone,
    }


def _scope_querysets(interaction) -> dict:
    return {
        "directions": (
            InteractionDirection.objects
            .filter(interaction=interaction, is_active=True)
            .select_related("direction")
            .order_by("added_at")
        ),
        "programs": (
            InteractionProgram.objects
            .filter(interaction=interaction, is_active=True)
            .select_related("program__direction")
            .order_by("added_at")
        ),
        "products": (
            InteractionProduct.objects
            .filter(interaction=interaction, is_active=True)
            .select_related("product", "interaction_program__program")
            .order_by("added_at")
        ),
        "licenses": (
            License.objects
            .filter(interaction_product__interaction=interaction, is_active=True)
            .select_related("contract", "interaction_product__product")
            .order_by("created_at")
        ),
    }


_SCOPE_SERIALIZERS = {
    "directions": lambda item: {"id": str(item.pk), "name": item.direction.name},
    "programs": lambda item: {
        "id": str(item.pk),
        "name": item.program.name,
        "direction": item.program.direction.name,
    },
    "products": lambda item: {
        "id": str(item.pk),
        "name": item.product.name,
        "program": item.interaction_program.program.name if item.interaction_program else "",
    },
    "licenses": lambda item: {
        "id": str(item.pk),
        "product": item.interaction_product.product.name,
        "contract_number": item.contract.contract_number,
        "signed_at": item.signed_at.isoformat() if item.signed_at else None,
        "valid_until_year": item.valid_until_year,
        "is_signed": item.is_signed,
    },
}


def _scope(interaction) -> dict:
    """Направления, программы, продукты и лицензии взаимодействия в формате документа."""
    return {
        key: [_SCOPE_SERIALIZERS[key](item) for item in queryset]
        for key, queryset in _scope_querysets(interaction).items()
    }


def _resolve_scope(interaction, document: dict) -> dict:
    """Проверяет выбранные элементы по `id` и заменяет их актуальными данными взаимодействия."""
    available = _scope(interaction)
    errors = {}
    resolved = {}
    for key, items in available.items():
        by_id = {item["id"]: item for item in items}
        selected_ids = [str(item.get("id", "")) for item in document[key]]
        unknown = [item_id for item_id in selected_ids if item_id not in by_id]
        if unknown:
            errors[key] = [f"Не относятся к взаимодействию: {', '.join(unknown)}."]
            continue
        selected = set(selected_ids)
        # Порядок — как во взаимодействии, дубли схлопываются.
        resolved[key] = [item for item in items if item["id"] in selected]
    if errors:
        raise serializers.ValidationError({"document": errors})
    return resolved


class CreateContractHandler:
    """
    Создаёт договор взаимодействия по данным из формы.

    Фронтенд присылает готовый JSON (`document`) — контекст рендера шаблона `template`.
    Выбранный DOCX заполняется JSON и сохраняется как текущий файл договора.
    """

    code = "contract.create"

    def initial(self, *, context, settings: dict) -> dict:
        """Черновик формы: шаблоны и всё, что известно о взаимодействии."""
        if not context.university and not context.b2c_client:
            raise ActionFeatureError("invalid_action_context")
        contacts = (
            InteractionContact.objects
            .filter(interaction=context.interaction, unlinked_at__isnull=True)
            .select_related("contact_person")
            .order_by("linked_at")
        )
        return {
            "templates": [{"id": item.pk, "name": item.name} for item in _contract_templates()],
            "contacts": [
                {
                    "id": link.contact_person.pk,
                    "full_name": link.contact_person.full_name,
                    "position": link.contact_person.position,
                }
                for link in contacts
            ],
            "document": {
                "contract_number": "",
                "contract_date": None,
                "city": getattr(context.university, "city", "") or "",
                "counterparty": _counterparty(context),
                "signatory": {"full_name": "", "position": "", "basis": ""},
                # По умолчанию в договор идёт весь состав взаимодействия.
                **_scope(context.interaction),
                "amount": None,
                "comment": "",
            },
        }

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        if not context.university and not context.b2c_client:
            raise ActionFeatureError("invalid_action_context")
        serializer = CreateContractPayloadSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        template = serializer.validated_data["template"]
        document = ContractDocumentSerializer(serializer.validated_data["document"]).data
        document.update(_resolve_scope(context.interaction, document))
        try:
            rendered_file = render_contract_template(template, document)
        except DocumentTemplateRenderError as error:
            raise serializers.ValidationError({"template": [str(error)]}) from error
        contract = Contract.objects.create(
            interaction=context.interaction,
            contract_number=document["contract_number"],
            file=rendered_file,
            file_name=rendered_file.name,
        )
        record_contract_file(contract, context.user)
        return ActionFeatureResult(
            "contract",
            contract.pk,
            {
                "contract_number": contract.contract_number,
                "template": {"id": str(template.pk), "name": template.name},
                "document": document,
                "file_generated": True,
            },
        )
