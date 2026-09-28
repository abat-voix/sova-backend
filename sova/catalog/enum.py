from django.db.models import TextChoices


class CatalogType(TextChoices):
    """Тип каталога/реестра для настраиваемого маппинга полей при импорте xls/xlsx."""

    ORGANIZATION = "organization", "Организации"
    VENDOR = "vendor", "Вендоры"
    DIRECTION = "direction", "Направления"
    PROGRAM = "program", "Программы"
    PRODUCT = "product", "Продукты"
    CONTACT_PERSON = "contact_person", "Ответственные от организации"
    CONTRACT_REGISTRY = "contract_registry", "Реестр договоров"
    # Файл «Пользователи» обучения: грузится через /api/training/learners/import/, здесь — только маппинг колонок
    LEARNER = "learner", "Обучающиеся"


class ContactChannel(TextChoices):
    """Предпочтительный способ связи с контактным лицом в организации."""

    EMAIL = "email", "Почта"
    TELEGRAM = "telegram", "Чат в Telegram"
    PHONE = "phone", "Телефон"


class AddressKind(TextChoices):
    """Тип адреса организации."""

    LEGAL = "legal", "Юридический"
    ACTUAL = "actual", "Фактический"


class PersonalDataAccessAction(TextChoices):
    """Что сделали с персональными данными B2C-клиента."""

    READ = "read", "Просмотр"
    UPDATE = "update", "Изменение"
