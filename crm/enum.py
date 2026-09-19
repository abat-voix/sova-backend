from django.db.models import TextChoices


class Audience(TextChoices):
    """Целевая аудитория workflow-шаблона."""

    B2B = "b2b", "Вузы"
    B2C = "b2c", "Физ/юрлица"


class ClientKind(TextChoices):
    """Тип B2C-клиента."""

    INDIVIDUAL = "individual", "Физлицо"
    LEGAL_ENTITY = "legal_entity", "Юрлицо"


class StageInstanceContextType(TextChoices):
    """На каком уровне создан StageInstance."""

    CONTACT = "contact", "Сделка целиком"
    IT_PROGRAM = "it_program", "ИТ-программа"
    IT_PRODUCT = "it_product", "ИТ-продукт"


class CatalogType(TextChoices):
    """Тип каталога для настраиваемого маппинга полей при импорте xls/xlsx."""

    UNIVERSITY = "university", "Вузы"
    IT_PRODUCT = "it_product", "ИТ-продукты"
    IT_DIRECTION = "it_direction", "ИТ-направления"
    RESPONSIBLE = "responsible", "Ответственные"
