from dataclasses import dataclass
from typing import NamedTuple

from sova.catalog.enum import CatalogType


@dataclass(frozen=True)
class ImportRowError:
    """Ошибка одной строки файла импорта каталога."""

    row_number: int
    message: str

    def __str__(self) -> str:
        return f"Строка {self.row_number}: {self.message}"


@dataclass(frozen=True)
class ImportRowWarning:
    """Предупреждение по строке файла импорта: строка загружена, но часть данных не применена."""

    row_number: int
    message: str

    def __str__(self) -> str:
        return f"Строка {self.row_number}: {self.message}"


class CatalogImportResult(NamedTuple):
    """Итог импорта файла: создано, обновлено и предупреждения по строкам."""

    created: int
    updated: int
    warnings: list[ImportRowWarning]


@dataclass(frozen=True)
class CatalogImportFields:
    """Канонические поля импорта одного типа каталога — допустимые значения `target_field` маппинга."""

    required: frozenset[str]
    optional: frozenset[str] = frozenset()

    @property
    def all(self) -> frozenset[str]:
        """Все допустимые поля: обязательные и необязательные."""
        return self.required | self.optional


# Ключи, которые понимают обработчики импорта в sova/catalog/services/ (по значению CatalogType).
CATALOG_IMPORT_FIELDS = {
    CatalogType.UNIVERSITY: CatalogImportFields(
        required=frozenset({
            "id", "ror", "name_en", "name", "short_name", "country_code", "type",
            "works_count", "cited_by_count", "city", "region", "lat", "lon", "homepage_url",
        }),
    ),
    # Справочник вендоров (name/external_code) или файл «вендор + продукты + контактное лицо» (Вендоры.xlsx).
    CatalogType.VENDOR: CatalogImportFields(
        required=frozenset({"name"}),
        optional=frozenset({
            "external_code", "is_active", "products",
            "contact_full_name", "contact_email", "contact_phone", "contact_telegram", "contact_position",
            "contact_channels",
        }),
    ),
    CatalogType.DIRECTION: CatalogImportFields(
        required=frozenset({"name", "external_code"}),
        optional=frozenset({"is_active"}),
    ),
    CatalogType.PROGRAM: CatalogImportFields(
        required=frozenset({"name", "direction"}),
        optional=frozenset({"is_active"}),
    ),
    CatalogType.PRODUCT: CatalogImportFields(
        required=frozenset({"name", "external_code", "vendor"}),
        optional=frozenset({"is_active", "programs"}),
    ),
    CatalogType.CONTACT_PERSON: CatalogImportFields(
        required=frozenset({"full_name", "university"}),
        optional=frozenset({"position", "email", "phone", "telegram", "channels"}),
    ),
    CatalogType.CONTRACT_REGISTRY: CatalogImportFields(
        required=frozenset({"university", "vendor", "product", "contract_number"}),
        optional=frozenset({
            "direction", "program", "license_signed", "license_valid_until_year", "university_contact",
            "manager_full_name", "draft_status", "draft_comment",
        }),
    ),
    # Обучающиеся и их персональные данные (файл «Пользователи»); email или телефон обязателен — проверяет обработчик
    CatalogType.LEARNER: CatalogImportFields(
        required=frozenset({"last_name", "first_name"}),
        optional=frozenset({
            "middle_name", "email", "phone", "gender", "birth_date",
            "last_name_dative", "first_name_dative", "middle_name_dative", "snils",
            "passport_series", "passport_number", "passport_issued_by", "passport_issued_at", "passport_division_code",
            "registration_region", "registration_locality", "registration_street", "registration_house",
            "registration_apartment", "registration_postcode", "education_level", "diploma_qualification",
            "diploma_institution", "diploma_last_name", "diploma_series", "diploma_number",
            "diploma_registration_number", "diploma_issued_at",
        }),
    ),
}

# Подписи канонических полей импорта для интерфейса маппинга (один ключ — одна подпись во всех типах).
CATALOG_IMPORT_FIELD_LABELS: dict[str, str] = {
    "id": "Идентификатор",
    "ror": "ROR",
    "name": "Название",
    "name_en": "Название (англ.)",
    "short_name": "Краткое название",
    "country_code": "Код страны",
    "type": "Тип",
    "works_count": "Число публикаций",
    "cited_by_count": "Число цитирований",
    "city": "Город",
    "region": "Регион",
    "lat": "Широта",
    "lon": "Долгота",
    "homepage_url": "Сайт",
    "external_code": "Внешний код",
    "is_active": "Активен",
    "products": "Продукты",
    "contact_full_name": "ФИО контакта",
    "contact_email": "E-mail контакта",
    "contact_phone": "Телефон контакта",
    "contact_telegram": "Telegram контакта",
    "contact_position": "Должность контакта",
    "contact_channels": "Способы связи контакта",
    "direction": "Направление",
    "vendor": "Вендор",
    "programs": "Программы",
    "full_name": "ФИО",
    "university": "Вуз",
    "position": "Должность",
    "email": "E-mail",
    "phone": "Телефон",
    "telegram": "Telegram",
    "channels": "Способы связи",
    "product": "Продукт",
    "contract_number": "Номер договора",
    "program": "Программа",
    "license_signed": "Лицензия подписана",
    "license_valid_until_year": "Лицензия действует до (год)",
    "university_contact": "Ответственный от вуза",
    "manager_full_name": "ФИО менеджера",
    "draft_status": "Статус проекта договора",
    "draft_comment": "Комментарий к проекту договора",
    "last_name": "Фамилия",
    "first_name": "Имя",
    "middle_name": "Отчество",
    "gender": "Пол",
    "birth_date": "Дата рождения",
    "last_name_dative": "Фамилия (дательный падеж)",
    "first_name_dative": "Имя (дательный падеж)",
    "middle_name_dative": "Отчество (дательный падеж)",
    "snils": "СНИЛС",
    "passport_series": "Серия паспорта",
    "passport_number": "Номер паспорта",
    "passport_issued_by": "Кем выдан паспорт",
    "passport_issued_at": "Дата выдачи паспорта",
    "passport_division_code": "Код подразделения",
    "registration_region": "Регион регистрации",
    "registration_locality": "Населённый пункт регистрации",
    "registration_street": "Улица регистрации",
    "registration_house": "Дом регистрации",
    "registration_apartment": "Квартира регистрации",
    "registration_postcode": "Индекс регистрации",
    "education_level": "Образование",
    "diploma_qualification": "Профессия по диплому",
    "diploma_institution": "Учебное заведение по диплому",
    "diploma_last_name": "Фамилия, указанная в дипломе",
    "diploma_series": "Серия диплома",
    "diploma_number": "Номер диплома",
    "diploma_registration_number": "Регистрационный номер диплома",
    "diploma_issued_at": "Дата выдачи диплома",
}
