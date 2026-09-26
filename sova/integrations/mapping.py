from rest_framework import serializers

from sova.integrations.enum import IntegrationDirection
from sova.integrations.registry import serializer_fields


MISSING = object()


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
    fields = serializer_fields(entity) or {}
    result, errors, warnings = {}, [], []
    for rule in rules:
        source, target = rule["sourcePath"], rule["targetField"]
        required, default = rule.get("required", False), rule.get("defaultValue")
        if direction == IntegrationDirection.INCOMING:
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
            field = fields[target]
            if field.read_only:
                errors.append(f"Поле доступно только для чтения: {target}")
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
