from rest_framework import serializers

from sova.interactions.enum import DocumentTemplateKind
from sova.interactions.models import Contract, DocumentTemplate, InteractionContact, InteractionProduct
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
    products = serializers.ListField(
        child=serializers.CharField(max_length=500), allow_empty=True, default=list,
    )
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, allow_null=True, default=None)
    comment = serializers.CharField(allow_blank=True, default="")


class CreateContractPayloadSerializer(serializers.Serializer):
    template = serializers.PrimaryKeyRelatedField(
        queryset=DocumentTemplate.objects.filter(kind=DocumentTemplateKind.CONTRACT, is_active=True),
    )
    document = ContractDocumentSerializer()


def _contract_templates():
    return DocumentTemplate.objects.filter(kind=DocumentTemplateKind.CONTRACT, is_active=True)


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


class CreateContractHandler:
    """
    Создаёт договор взаимодействия по данным из формы.

    Фронтенд присылает готовый JSON (`document`) — контекст рендера шаблона `template`.
    Рендер через docxtpl пока не подключён: договор создаётся без файла, JSON сохраняется
    в результате исполнения feature, чтобы по нему можно было сформировать файл позже.
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
        if context.interaction_product:
            products = [context.interaction_product]
        else:
            products = (
                InteractionProduct.objects
                .filter(interaction=context.interaction, is_active=True)
                .select_related("product")
                .order_by("added_at")
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
                "products": [item.product.name for item in products],
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
        contract = Contract.objects.create(
            interaction=context.interaction,
            contract_number=document["contract_number"],
        )
        # TODO: рендер `template.file` через docxtpl с контекстом `document` → Contract.file.
        return ActionFeatureResult(
            "contract",
            contract.pk,
            {
                "contract_number": contract.contract_number,
                "template": {"id": str(template.pk), "name": template.name},
                "document": document,
                "file_generated": False,
            },
        )
