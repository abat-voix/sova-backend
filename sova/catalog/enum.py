from django.db.models import TextChoices


class ClientKind(TextChoices):
    """Тип B2C-клиента."""

    INDIVIDUAL = "individual", "Физлицо"
    LEGAL_ENTITY = "legal_entity", "Юрлицо"


class CatalogType(TextChoices):
    """Тип каталога/реестра для настраиваемого маппинга полей при импорте xls/xlsx."""

    UNIVERSITY = "university", "Вузы"
    VENDOR = "vendor", "Вендоры"
    DIRECTION = "direction", "Направления"
    PROGRAM = "program", "Программы"
    PRODUCT = "product", "Продукты"
    CONTACT_PERSON = "contact_person", "Ответственные от вуза"
    CONTRACT_REGISTRY = "contract_registry", "Реестр договоров"


class ContactChannel(TextChoices):
    """Предпочтительный способ связи с контактным лицом в организации."""

    EMAIL = "email", "Почта"
    TELEGRAM = "telegram", "Чат в Telegram"
    PHONE = "phone", "Телефон"
