"""Рендер DOCX-шаблонов из JSON-контекста документа."""

from io import BytesIO

from django.core.files.base import ContentFile
from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined, TemplateError, UndefinedError

from sova.interactions.enum import DocumentTemplateKind
from sova.interactions.models import DocumentTemplate


class DocumentTemplateRenderError(ValueError):
    """Шаблон нельзя использовать с переданными данными."""


def _printable(value):
    """Пустые необязательные поля печатаются пустой строкой, а не `None`."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return {key: _printable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_printable(item) for item in value]
    return value


def render_contract_template(template: DocumentTemplate, document: dict) -> ContentFile:
    """Подставить поля JSON в DOCX; ключи документа доступны прямо в `{{ ... }}`."""
    if template.kind != DocumentTemplateKind.CONTRACT or not template.is_active:
        raise DocumentTemplateRenderError("Выбранный шаблон договора недоступен.")
    if not template.file:
        raise DocumentTemplateRenderError("У шаблона договора не загружен файл DOCX.")
    if not template.file.name.lower().endswith(".docx"):
        raise DocumentTemplateRenderError("Файл шаблона должен иметь формат DOCX.")

    try:
        with template.file.open("rb") as source:
            docx = DocxTemplate(BytesIO(source.read()))
        docx.render(_printable(document), jinja_env=Environment(undefined=StrictUndefined, autoescape=True))
        output = BytesIO()
        docx.save(output)
    except UndefinedError as error:
        raise DocumentTemplateRenderError(
            f"В шаблоне используется поле без данных: {error}"
        ) from error
    except TemplateError as error:
        raise DocumentTemplateRenderError(
            f"Некорректный синтаксис шаблона: {error}"
        ) from error
    except Exception as error:
        raise DocumentTemplateRenderError(
            "Файл шаблона повреждён или недоступен."
        ) from error

    return ContentFile(output.getvalue(), name="Договор.docx")
