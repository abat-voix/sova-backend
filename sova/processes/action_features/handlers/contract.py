from django.db.models import Count
from django.urls import reverse
from rest_framework import serializers

from sova.interactions.api.serializers.contract import WriteContractSerializer
from sova.catalog.services.contact_affiliation import contact_affiliation_service
from sova.catalog.services.organization_address import organization_address_service
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
from sova.core.validators import validate_inn, validate_phone


class ContractCounterpartySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=500)
    short_name = serializers.CharField(max_length=255, allow_blank=True, default="")
    inn = serializers.CharField(max_length=12, allow_blank=True, default="", validators=[validate_inn])
    address = serializers.CharField(max_length=1000, allow_blank=True, default="")
    email = serializers.EmailField(allow_blank=True, default="")
    phone = serializers.CharField(max_length=50, allow_blank=True, default="", validators=[validate_phone])


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
    if context.organization:
        organization = context.organization
        # В договор — юридический адрес; если его нет, фактический
        address = organization_address_service.legal(organization) or organization_address_service.actual(organization)
        return {
            "name": organization.name,
            "short_name": organization.short_name,
            "inn": organization.inn or "",
            "address": address.full_text if address else "",
            "email": organization.email,
            "phone": organization.phone,
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
        if not context.organization and not context.b2c_client:
            raise ActionFeatureError("invalid_action_context")
        contacts = contact_affiliation_service.annotate_interaction_position(
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
                    "position": link.position,
                }
                for link in contacts
            ],
            "document": {
                "contract_number": "",
                "contract_date": None,
                "city": organization_address_service.city(context.organization) if context.organization else "",
                "counterparty": _counterparty(context),
                "signatory": {"full_name": "", "position": "", "basis": ""},
                # По умолчанию в договор идёт весь состав взаимодействия.
                **_scope(context.interaction),
                "amount": None,
                "comment": "",
            },
        }

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        if not context.organization and not context.b2c_client:
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


def _contract_id(data: dict):
    try:
        return serializers.UUIDField(required=True).run_validation(data.get("contract"))
    except serializers.ValidationError as error:
        raise ActionFeatureError(
            "invalid_contract",
            "Укажите корректный идентификатор договора.",
            400,
        ) from error


def _contract_for_interaction(context, data: dict) -> Contract:
    contract = Contract.objects.filter(
        pk=_contract_id(data),
        interaction=context.interaction,
    ).first()
    if contract is None:
        raise ActionFeatureError(
            "contract_not_found",
            "Договор текущего взаимодействия не найден.",
            404,
        )
    return contract


def _contract_data(contract: Contract) -> dict:
    return {
        "contract_number": contract.contract_number,
        "sent_at": contract.sent_at.isoformat() if contract.sent_at else None,
        "corrected_at": (
            contract.corrected_at.isoformat() if contract.corrected_at else None
        ),
        "signed_at": contract.signed_at.isoformat() if contract.signed_at else None,
        "file_name": contract.file_name,
        "download_url": (
            reverse("interactions:contract-download", args=[contract.pk])
            if contract.file
            else None
        ),
        "files_count": contract.files.count(),
    }


def _update_contract(contract: Contract, data: dict) -> Contract:
    serializer = WriteContractSerializer(
        contract,
        data=data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    return serializer.save()


class ContractOperationHandler:
    """Общие начальные данные для операций над договорами взаимодействия."""

    code = ""

    def initial(self, *, context, settings: dict) -> dict:
        contracts = Contract.objects.filter(interaction=context.interaction)
        if self.code == "contract.sign":
            contracts = contracts.filter(signed_at__isnull=True)
        elif self.code == "contract.mark_sent":
            contracts = contracts.filter(
                sent_at__isnull=True,
                signed_at__isnull=True,
            )
        elif self.code == "contract.mark_corrected":
            contracts = contracts.filter(
                sent_at__isnull=False,
                signed_at__isnull=True,
            )
        contracts = contracts.annotate(files_count=Count("files")).order_by(
            "-created_at",
            "pk",
        )
        return {
            "contracts": [
                {
                    "id": item.pk,
                    "contract_number": item.contract_number,
                    "sent_at": item.sent_at,
                    "corrected_at": item.corrected_at,
                    "signed_at": item.signed_at,
                    "file_name": item.file_name,
                    "download_url": (
                        reverse("interactions:contract-download", args=[item.pk])
                        if item.file
                        else None
                    ),
                    "files_count": item.files_count,
                }
                for item in contracts
            ],
        }


class UpdateContractHandler(ContractOperationHandler):
    code = "contract.update"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        contract = _contract_for_interaction(context, data)
        number = serializers.CharField(
            max_length=255,
            allow_blank=True,
            trim_whitespace=True,
        ).run_validation(data.get("contract_number"))
        contract = _update_contract(contract, {"contract_number": number})
        return ActionFeatureResult("contract", contract.pk, _contract_data(contract))


class ContractDateHandler(ContractOperationHandler):
    date_field = ""

    def validate_contract(self, contract: Contract) -> None:
        return None

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        contract = _contract_for_interaction(context, data)
        self.validate_contract(contract)
        value = serializers.DateField(required=True).run_validation(
            data.get(self.date_field),
        )
        contract = _update_contract(contract, {self.date_field: value})
        return ActionFeatureResult("contract", contract.pk, _contract_data(contract))


class SignContractHandler(ContractDateHandler):
    code = "contract.sign"
    date_field = "signed_at"

    def validate_contract(self, contract: Contract) -> None:
        if contract.signed_at is not None:
            raise ActionFeatureError(
                "contract_already_signed",
                "Договор уже отмечен подписанным.",
                409,
            )


class MarkContractSentHandler(ContractDateHandler):
    code = "contract.mark_sent"
    date_field = "sent_at"

    def validate_contract(self, contract: Contract) -> None:
        if contract.sent_at is not None:
            raise ActionFeatureError(
                "contract_already_sent",
                "Дата отправки договора уже указана.",
                409,
            )
        if contract.signed_at is not None:
            raise ActionFeatureError(
                "contract_already_signed",
                "Нельзя отметить отправку уже подписанного договора.",
                409,
            )


class MarkContractCorrectedHandler(ContractDateHandler):
    code = "contract.mark_corrected"
    date_field = "corrected_at"

    def validate_contract(self, contract: Contract) -> None:
        if contract.sent_at is None:
            raise ActionFeatureError(
                "contract_not_sent",
                "Сначала отметьте отправку договора.",
                409,
            )
        if contract.signed_at is not None:
            raise ActionFeatureError(
                "contract_already_signed",
                "Нельзя отметить доработку уже подписанного договора.",
                409,
            )


class UploadContractFileHandler(ContractOperationHandler):
    code = "contract.file.upload"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        contract = _contract_for_interaction(context, data)
        uploaded_file = serializers.FileField(required=True).run_validation(
            data.get("file"),
        )
        contract = _update_contract(contract, {"file": uploaded_file})
        record_contract_file(contract, context.user)
        return ActionFeatureResult("contract", contract.pk, _contract_data(contract))
