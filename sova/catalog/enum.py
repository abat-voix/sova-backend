from django.db.models import TextChoices


class ClientKind(TextChoices):
    """Тип B2C-клиента."""

    INDIVIDUAL = "individual", "Физлицо"
    LEGAL_ENTITY = "legal_entity", "Юрлицо"


class CatalogType(TextChoices):
    """Тип каталога для настраиваемого маппинга полей при импорте xls/xlsx."""

    UNIVERSITY = "university", "Вузы"
    PRODUCT = "product", "Продукты"
    DIRECTION = "direction", "Направления"
    RESPONSIBLE = "responsible", "Ответственные"
