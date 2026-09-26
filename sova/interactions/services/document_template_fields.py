"""Поля JSON-контекста, доступные в DOCX-шаблоне договора."""

from sova.interactions.enum import DocumentTemplateKind


def _field(path: str, label: str, type_: str = "string") -> dict:
    return {
        "path": path,
        "label": label,
        "type": type_,
        "snippet": "{{ " + path + " }}",
    }


def _object(path: str, label: str, fields: tuple[tuple[str, str, str], ...]) -> list[dict]:
    result = [{"path": path, "label": label, "type": "object", "snippet": ""}]
    result.extend(_field(f"{path}.{name}", title, type_) for name, title, type_ in fields)
    return result


def _collection(
    path: str,
    label: str,
    item_name: str,
    fields: tuple[tuple[str, str, str], ...],
) -> list[dict]:
    example_field = next((name for name, _, _ in fields if name != "id"), fields[0][0])
    loop_start = "{% for " + item_name + " in " + path + " %}"
    loop_end = "{% endfor %}"
    result = [{
        "path": path,
        "label": label,
        "type": "array",
        "snippet": f"{loop_start}\n{{{{ {item_name}.{example_field} }}}}\n{loop_end}",
    }]
    result.extend(
        {
            "path": f"{path}[].{name}",
            "label": title,
            "type": type_,
            "snippet": f"{loop_start}\n{{{{ {item_name}.{name} }}}}\n{loop_end}",
        }
        for name, title, type_ in fields
    )
    return result


def contract_template_fields() -> dict:
    """Каталог полей для `contract.create`; `snippet` можно вставить в DOCX."""
    fields = [
        _field("contract_number", "Номер договора"),
        _field("contract_date", "Дата договора", "date"),
        _field("city", "Город"),
        *_object("counterparty", "Контрагент", (
            ("name", "Полное наименование", "string"),
            ("short_name", "Краткое наименование", "string"),
            ("inn", "ИНН", "string"),
            ("address", "Адрес", "string"),
            ("email", "Email", "string"),
            ("phone", "Телефон", "string"),
        )),
        *_object("signatory", "Подписант", (
            ("full_name", "ФИО", "string"),
            ("position", "Должность", "string"),
            ("basis", "Основание полномочий", "string"),
        )),
        *_collection("directions", "Направления", "direction", (
            ("id", "ID направления", "string"),
            ("name", "Название направления", "string"),
        )),
        *_collection("programs", "Программы", "program", (
            ("id", "ID программы", "string"),
            ("name", "Название программы", "string"),
            ("direction", "Направление программы", "string"),
        )),
        *_collection("products", "Продукты", "product", (
            ("id", "ID продукта", "string"),
            ("name", "Название продукта", "string"),
            ("program", "Программа продукта", "string"),
        )),
        *_collection("licenses", "Лицензии", "license", (
            ("id", "ID лицензии", "string"),
            ("product", "Продукт лицензии", "string"),
            ("contract_number", "Номер договора лицензии", "string"),
            ("signed_at", "Дата подписания", "date"),
            ("valid_until_year", "Год окончания", "integer"),
            ("is_signed", "Подписана", "boolean"),
        )),
        _field("amount", "Сумма договора", "decimal"),
        _field("comment", "Комментарий"),
    ]
    return {"kind": DocumentTemplateKind.CONTRACT, "fields": fields}
