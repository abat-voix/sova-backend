from django.db.models import TextChoices


class DocumentTemplateKind(TextChoices):
    """Тип документа, который рендерится из шаблона (docxtpl)."""

    CONTRACT = "contract", "Договор"
