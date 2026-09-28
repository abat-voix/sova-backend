from dataclasses import dataclass, field

from django.db.models import F, Func, Q, Value

from sova.catalog.exceptions import CatalogImportError
from sova.catalog.models import ContactPerson
from sova.catalog.services.contact_affiliation import ContactOwner, contact_affiliation_service
from sova.core.text import phone_key

# Сколько возможных дублей показывать: подсказка, а не поиск.
MAX_POSSIBLE_DUPLICATES = 10


@dataclass(frozen=True)
class ContactMatch:
    """Итог сопоставления строки импорта с людьми: найденный человек (None — нужен новый) и возможные дубли."""

    contact: ContactPerson | None
    possible_duplicates: list[ContactPerson] = field(default_factory=list)


class ContactMatchingService:
    """
    Сопоставление людей: один ли это человек и кто похож на него.

    Тёзки по умолчанию — разные люди: лучше дубль, который можно слить, чем ошибочно слитые люди.
    Надёжный признак — email. Телефон и Telegram — только дополнительная проверка (номер и ник меняются):
    ими выбирают одного из тёзок в организации и усиливают подсказку о дубле.
    """

    def match_for_import(
        self,
        organization: ContactOwner,
        full_name: str,
        email: str = "",
        phone: str = "",
        telegram: str = "",
    ) -> ContactMatch:
        """
        Человек для строки импорта организации.

        1) email совпал ровно с одним человеком — он; 2) иначе тёзка среди людей этой организации: один — он,
        несколько — уточнение телефоном/Telegram, не помогло — `CatalogImportError`; 3) иначе нового человека
        создаёт вызывающий, а здесь — возможные дубли для предупреждения.

        Строка организации блокируется до конца транзакции: параллельный импорт не создаст второго такого же человека.
        """
        type(organization).objects.select_for_update().filter(pk=organization.pk).first()

        if email:
            by_email = list(ContactPerson.objects.filter(email__iexact=email)[:2])
            if len(by_email) == 1:
                return ContactMatch(contact=by_email[0])

        namesakes = list(
            contact_affiliation_service.contacts_for(organization=organization).filter(full_name__iexact=full_name)
        )
        if len(namesakes) == 1:
            return ContactMatch(contact=namesakes[0])
        if namesakes:
            narrowed = [contact for contact in namesakes if self._same_phone_or_telegram(contact, phone, telegram)]
            if len(narrowed) == 1:
                return ContactMatch(contact=narrowed[0])
            raise CatalogImportError(
                f"у организации {organization} несколько контактных лиц {full_name}: уточните email или телефон"
            )

        return ContactMatch(
            contact=None,
            possible_duplicates=self.possible_duplicates(full_name=full_name, phone=phone, telegram=telegram),
        )

    def possible_duplicates(
        self,
        full_name: str = "",
        email: str = "",
        phone: str = "",
        telegram: str = "",
        exclude_id=None,
    ) -> list[ContactPerson]:
        """Люди с тем же ФИО, email, телефоном или Telegram — подсказка «возможно, это он»; сначала — совпавшие по нескольким признакам."""
        condition = Q()
        if full_name:
            condition |= Q(full_name__iexact=full_name)
        if email:
            condition |= Q(email__iexact=email)
        if telegram:
            condition |= Q(telegram__iexact=telegram)
        candidates = list(ContactPerson.objects.filter(condition)) if condition else []

        key = phone_key(phone)
        if key:
            # Телефоны хранятся как введены: в БД отбираются по цифрам номера без кода страны, точно — по ключу.
            by_phone = ContactPerson.objects.annotate(
                phone_digits=Func(F("phone"), Value(r"\D"), Value(""), Value("g"), function="regexp_replace")
            ).filter(phone_digits__endswith=key[-10:])
            candidates += [contact for contact in by_phone if phone_key(contact.phone) == key]

        scores: dict = {}
        unique: dict = {}
        for contact in candidates:
            if contact.pk == exclude_id:
                continue
            unique[contact.pk] = contact
            scores[contact.pk] = scores.get(contact.pk, 0) + 1
        ordered = sorted(unique.values(), key=lambda contact: (-scores[contact.pk], contact.full_name))
        return ordered[:MAX_POSSIBLE_DUPLICATES]

    def _same_phone_or_telegram(self, contact: ContactPerson, phone: str, telegram: str) -> bool:
        """Совпадение телефона (по ключу) или Telegram (без учёта регистра); пустые значения не совпадают."""
        if phone and contact.phone and phone_key(contact.phone) == phone_key(phone):
            return True
        return bool(telegram and contact.telegram and contact.telegram.casefold() == telegram.casefold())


contact_matching_service = ContactMatchingService()
