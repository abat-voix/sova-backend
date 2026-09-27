from django.db import transaction
from rest_framework import serializers

from sova.integrations.enum import IntegrationDirection
from sova.integrations.registry import ENTITIES, incoming_fields, serializer_fields


MISSING = object()


class MappingProcessingError(Exception):
    """Payload не удалось превратить в сущность CRM по правилам маппинга."""

    def __init__(self, errors, warnings=()):
        super().__init__("\n".join(errors))
        self.errors = list(errors)
        self.warnings = list(warnings)


def get_json_path(payload, path):
    if not path.startswith("$."):
        return MISSING
    segments = path[2:].split(".")

    def resolve(current, index):
        if index == len(segments):
            return current
        segment = segments[index]
        is_array = segment.endswith("[]")
        key = segment[:-2] if is_array else segment
        if not isinstance(current, dict) or key not in current:
            return MISSING
        value = current[key]
        if is_array:
            if not isinstance(value, list):
                return MISSING
            if index == len(segments) - 1:
                return value
            resolved = [resolve(item, index + 1) for item in value]
            return MISSING if any(item is MISSING for item in resolved) else resolved
        return resolve(value, index + 1)

    return resolve(payload, 0)


def set_json_path(result, path, value):
    current = result
    parts = path[2:].split(".")
    for part in parts[:-1]:
        key = part.removesuffix("[]")
        current = current.setdefault(key, {})
    current[parts[-1].removesuffix("[]")] = value


def preview_mapping(*, entity, direction, rules, payload):
    is_incoming = direction == IntegrationDirection.INCOMING
    fields = (incoming_fields(entity) if is_incoming else serializer_fields(entity)) or {}
    result, errors, warnings = {}, [], []
    for rule in rules:
        source, target = rule["sourcePath"], rule["targetField"]
        required, default = rule.get("required", False), rule.get("defaultValue")
        if is_incoming:
            value = get_json_path(payload, source)
            if value is MISSING:
                if default is not None:
                    value = default
                elif required:
                    errors.append(f"Отсутствует обязательное значение: {source}")
                    continue
                else:
                    warnings.append(f"Путь не найден: {source}")
                    continue
            field = fields.get(target)
            if field is None:
                errors.append(f"Поле нельзя заполнить из входящего сообщения: {target}")
                continue
            try:
                field.run_validation(value)
            except serializers.ValidationError:
                errors.append(f"Несовместимый тип для поля: {target}")
                continue
            result[target] = value
        else:
            value = payload.get(source, MISSING)
            if value is MISSING:
                if default is not None:
                    value = default
                elif required:
                    errors.append(f"Отсутствует обязательное значение: {source}")
                    continue
                else:
                    warnings.append(f"Поле не найдено: {source}")
                    continue
            set_json_path(result, target, value)
    return {"result": result, "errors": errors, "warnings": warnings}


def _flatten_errors(errors, prefix=""):
    if isinstance(errors, dict):
        return [item for key, value in errors.items() for item in _flatten_errors(value, f"{prefix}{key}: ")]
    if isinstance(errors, list):
        return [item for value in errors for item in _flatten_errors(value, prefix)]
    return [f"{prefix}{errors}"]


def _apply_item(entity, mapping, item):
    """Один JSON-объект → одна сущность CRM; транзакцию открывает вызывающий."""
    preview = preview_mapping(
        entity=mapping.entity, direction=IntegrationDirection.INCOMING, rules=mapping.rules, payload=item
    )
    if preview["errors"]:
        raise MappingProcessingError(preview["errors"], preview["warnings"])
    serializer = entity.write_serializer(data=preview["result"])
    if not serializer.is_valid():
        raise MappingProcessingError(_flatten_errors(serializer.errors), preview["warnings"])
    instance = serializer.save()
    return {"entity": mapping.entity, "id": str(instance.pk)}, preview["warnings"]


def apply_incoming_mapping(mapping, payload):
    """
    Разбирает payload по правилам маппинга и создаёт сущности CRM.

    Объект — одна сущность. Массив — по сущности на элемент: `null` пропускается, каждый элемент в своей
    транзакции, ошибки одного не откатывают остальные. Ошибки собираются в `errors`, а не бросаются.
    """
    entity = ENTITIES.get(mapping.entity)
    if entity is None or entity.write_serializer is None:
        raise MappingProcessingError([f"Сущность «{mapping.entity}» нельзя создать из входящего сообщения."])
    is_batch = isinstance(payload, list)
    created, errors, warnings = [], [], []
    for index, item in enumerate(payload if is_batch else [payload], start=1):
        prefix = f"Элемент {index}: " if is_batch else ""
        if item is None and is_batch:
            warnings.append(f"{prefix}пустой элемент пропущен")
            continue
        if not isinstance(item, dict):
            errors.append(f"{prefix}ожидается JSON-объект")
            continue
        try:
            with transaction.atomic():
                result, item_warnings = _apply_item(entity, mapping, item)
        except MappingProcessingError as exc:
            errors += [prefix + error for error in exc.errors]
            warnings += [prefix + warning for warning in exc.warnings]
            continue
        created.append(result)
        warnings += [prefix + warning for warning in item_warnings]
    return {"created": created, "errors": errors, "warnings": warnings}
