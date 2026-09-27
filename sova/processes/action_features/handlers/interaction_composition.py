from rest_framework import serializers

from sova.catalog.models import Direction, Product, Program
from sova.interactions.models import (
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
)
from sova.processes.action_features.base import ActionFeatureResult
from sova.processes.action_features.errors import ActionFeatureError


def _uuid(data: dict, field: str):
    try:
        return serializers.UUIDField(required=True).run_validation(data.get(field))
    except serializers.ValidationError as error:
        raise ActionFeatureError(
            f"invalid_{field}",
            "Укажите корректный идентификатор.",
            400,
        ) from error


def _optional_uuid(data: dict, field: str):
    value = data.get(field)
    if value in (None, ""):
        return None
    return _uuid(data, field)


def _composition_initial(interaction) -> dict:
    directions = list(
        InteractionDirection.objects.filter(interaction=interaction, is_active=True)
        .select_related("direction")
        .order_by("added_at", "pk")
    )
    programs = list(
        InteractionProgram.objects.filter(interaction=interaction, is_active=True)
        .select_related("program", "program__direction")
        .order_by("added_at", "pk")
    )
    products = list(
        InteractionProduct.objects.filter(interaction=interaction, is_active=True)
        .select_related("product", "interaction_program")
        .order_by("added_at", "pk")
    )
    product_counts = {}
    for product in products:
        if product.interaction_program_id is not None:
            product_counts[product.interaction_program_id] = (
                product_counts.get(product.interaction_program_id, 0) + 1
            )
    program_counts = {}
    for program in programs:
        direction_id = program.program.direction_id
        program_counts[direction_id] = program_counts.get(direction_id, 0) + 1

    return {
        "directions": [
            {
                "id": item.pk,
                "catalog_id": item.direction_id,
                "name": item.direction.name,
                "related_programs_count": program_counts.get(item.direction_id, 0),
            }
            for item in directions
        ],
        "programs": [
            {
                "id": item.pk,
                "catalog_id": item.program_id,
                "name": item.program.name,
                "direction": {
                    "id": item.program.direction_id,
                    "name": item.program.direction.name,
                },
                "related_products_count": product_counts.get(item.pk, 0),
            }
            for item in programs
        ],
        "products": [
            {
                "id": item.pk,
                "catalog_id": item.product_id,
                "name": item.product.name,
                "interaction_program": item.interaction_program_id,
            }
            for item in products
        ],
    }


def _sync(interaction) -> None:
    # Реестр feature загружается сервисом доски, который входит в тот же пакет
    # services. Отложенный импорт не создаёт цикл при старте Django.
    from sova.processes.services.engine import workflow_engine_service

    workflow_engine_service.sync_interaction(interaction_id=interaction.pk)


class CompositionHandler:
    def initial(self, *, context, settings: dict) -> dict:
        return _composition_initial(context.interaction)


class AddInteractionDirectionHandler(CompositionHandler):
    code = "interaction_direction.add"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        direction_id = _uuid(data, "direction")
        direction = Direction.objects.filter(pk=direction_id, is_active=True).first()
        if direction is None:
            raise ActionFeatureError(
                "direction_not_found",
                "Активное направление не найдено.",
                404,
            )
        item, created = InteractionDirection.objects.get_or_create(
            interaction=context.interaction,
            direction=direction,
            defaults={"is_active": True},
        )
        if not created and item.is_active:
            raise ActionFeatureError(
                "direction_already_added",
                "Направление уже добавлено во взаимодействие.",
                409,
            )
        if not created:
            item.is_active = True
            item.save(update_fields=("is_active",))
        _sync(context.interaction)
        return ActionFeatureResult(
            "interaction_direction",
            item.pk,
            {"name": direction.name, "catalog_id": str(direction.pk), "is_active": True},
        )


class RemoveInteractionDirectionHandler(CompositionHandler):
    code = "interaction_direction.remove"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        item_id = _uuid(data, "interaction_direction")
        item = (
            InteractionDirection.objects.filter(
                pk=item_id,
                interaction=context.interaction,
                is_active=True,
            )
            .select_related("direction")
            .first()
        )
        if item is None:
            raise ActionFeatureError(
                "direction_not_found",
                "Активное направление взаимодействия не найдено.",
                404,
            )
        item.is_active = False
        item.save(update_fields=("is_active",))
        _sync(context.interaction)
        return ActionFeatureResult(
            "interaction_direction",
            item.pk,
            {
                "name": item.direction.name,
                "catalog_id": str(item.direction_id),
                "is_active": False,
            },
        )


class AddInteractionProgramHandler(CompositionHandler):
    code = "interaction_program.add"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        program_id = _uuid(data, "program")
        program = Program.objects.select_related("direction").filter(
            pk=program_id,
            is_active=True,
        ).first()
        if program is None:
            raise ActionFeatureError(
                "program_not_found",
                "Активная программа не найдена.",
                404,
            )
        if not InteractionDirection.objects.filter(
            interaction=context.interaction,
            direction=program.direction,
            is_active=True,
        ).exists():
            raise ActionFeatureError(
                "program_direction_missing",
                "Сначала добавьте направление выбранной программы.",
                409,
            )
        item, created = InteractionProgram.objects.get_or_create(
            interaction=context.interaction,
            program=program,
            defaults={"is_active": True},
        )
        if not created and item.is_active:
            raise ActionFeatureError(
                "program_already_added",
                "Программа уже добавлена во взаимодействие.",
                409,
            )
        if not created:
            item.is_active = True
            item.save(update_fields=("is_active",))
        _sync(context.interaction)
        return ActionFeatureResult(
            "interaction_program",
            item.pk,
            {
                "name": program.name,
                "catalog_id": str(program.pk),
                "direction": {
                    "id": str(program.direction_id),
                    "name": program.direction.name,
                },
                "is_active": True,
            },
        )


class RemoveInteractionProgramHandler(CompositionHandler):
    code = "interaction_program.remove"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        item_id = _uuid(data, "interaction_program")
        item = (
            InteractionProgram.objects.filter(
                pk=item_id,
                interaction=context.interaction,
                is_active=True,
            )
            .select_related("program", "program__direction")
            .first()
        )
        if item is None:
            raise ActionFeatureError(
                "program_not_found",
                "Активная программа взаимодействия не найдена.",
                404,
            )
        item.is_active = False
        item.save(update_fields=("is_active",))
        _sync(context.interaction)
        return ActionFeatureResult(
            "interaction_program",
            item.pk,
            {
                "name": item.program.name,
                "catalog_id": str(item.program_id),
                "direction": {
                    "id": str(item.program.direction_id),
                    "name": item.program.direction.name,
                },
                "is_active": False,
            },
        )


class AddInteractionProductHandler(CompositionHandler):
    code = "interaction_product.add"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        product_id = _uuid(data, "product")
        product = Product.objects.filter(pk=product_id, is_active=True).first()
        if product is None:
            raise ActionFeatureError(
                "product_not_found",
                "Активный продукт не найден.",
                404,
            )
        interaction_program_id = _optional_uuid(data, "interaction_program")
        interaction_program = None
        if interaction_program_id is not None:
            interaction_program = (
                InteractionProgram.objects.filter(
                    pk=interaction_program_id,
                    interaction=context.interaction,
                    is_active=True,
                )
                .select_related("program")
                .first()
            )
            if interaction_program is None:
                raise ActionFeatureError(
                    "interaction_program_not_found",
                    "Активная программа взаимодействия не найдена.",
                    404,
                )
            if not product.programs.filter(pk=interaction_program.program_id).exists():
                raise ActionFeatureError(
                    "product_outside_program",
                    "Продукт не входит в выбранную программу.",
                    400,
                )
        item, created = InteractionProduct.objects.get_or_create(
            interaction=context.interaction,
            product=product,
            defaults={
                "interaction_program": interaction_program,
                "is_active": True,
            },
        )
        if not created and item.is_active:
            raise ActionFeatureError(
                "product_already_added",
                "Продукт уже добавлен во взаимодействие.",
                409,
            )
        if not created:
            item.interaction_program = interaction_program
            item.is_active = True
            item.full_clean()
            item.save(update_fields=("interaction_program", "is_active"))
        _sync(context.interaction)
        return ActionFeatureResult(
            "interaction_product",
            item.pk,
            {
                "name": product.name,
                "catalog_id": str(product.pk),
                "interaction_program": (
                    str(interaction_program.pk) if interaction_program else None
                ),
                "is_active": True,
            },
        )


class RemoveInteractionProductHandler(CompositionHandler):
    code = "interaction_product.remove"

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        item_id = _uuid(data, "interaction_product")
        item = (
            InteractionProduct.objects.filter(
                pk=item_id,
                interaction=context.interaction,
                is_active=True,
            )
            .select_related("product")
            .first()
        )
        if item is None:
            raise ActionFeatureError(
                "product_not_found",
                "Активный продукт взаимодействия не найден.",
                404,
            )
        item.is_active = False
        item.save(update_fields=("is_active",))
        _sync(context.interaction)
        return ActionFeatureResult(
            "interaction_product",
            item.pk,
            {
                "name": item.product.name,
                "catalog_id": str(item.product_id),
                "interaction_program": (
                    str(item.interaction_program_id)
                    if item.interaction_program_id is not None
                    else None
                ),
                "is_active": False,
            },
        )
