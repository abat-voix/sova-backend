from dataclasses import dataclass

from sova.catalog.models import ContactPerson
from sova.catalog.services.contact_affiliation import Affiliation, Organization, contact_affiliation_service
from sova.catalog.services.contact_matching import contact_matching_service
from sova.catalog.services.import_file import import_file_service
from sova.core.text import normalize_telegram, text_key


@dataclass(frozen=True)
class ContactRow:
    """Контактное лицо из строки файла; None — колонки нет в файле (значение не меняется)."""

    full_name: str
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    position: str | None = None
    channels: list[str] | None = None


@dataclass(frozen=True)
class ContactImportResult:
    """Связь человека с организацией после загрузки строки: создана ли она и предупреждения по строке."""

    affiliation: Affiliation
    created: bool
    warnings: list[str]


class ContactImportService:
    """
    Загрузка контактного лица организации из строки файла импорта.

    Человек сопоставляется `ContactMatchingService` (email → тёзка в организации → новый человек). Данные человека
    (email, телефон, Telegram) приходят из разных файлов и организаций, поэтому пустая ячейка их не стирает, а
    заполненная — перезаписывает (номер мог смениться). ФИО переписывается только при совпадении без учёта регистра:
    человек, найденный по email, не переименовывается. Должность и способы связи принадлежат связи с организацией
    этого файла: колонка есть — значение из файла, даже пустое.

    Выключенный человек, найденный или получивший связь по строке файла, включается: раз он есть в файле
    организации, он с ней работает.
    """

    def parse(self, row: dict, prefix: str = "") -> ContactRow | None:
        """
        Контакт из канонических ключей строки (`{prefix}full_name`, `{prefix}email`, …); нет ФИО — None.

        Контактные данные без ФИО — ValueError: непонятно, к кому они относятся.
        """
        values = {
            name: row[f"{prefix}{key}"] if f"{prefix}{key}" in row else None
            for name, key in (
                ("email", "email"),
                ("phone", "phone"),
                ("telegram", "telegram"),
                ("position", "position"),
                ("channels", "channels"),
            )
        }
        full_name = import_file_service.to_text(row.get(f"{prefix}full_name"))
        if not full_name:
            if any(import_file_service.to_text(value) for value in values.values()):
                raise ValueError(f"заполнены данные контактного лица, но не заполнено поле {prefix}full_name")
            return None

        text = {
            name: None if values[name] is None else import_file_service.to_text(values[name])
            for name in ("email", "phone", "position")
        }
        return ContactRow(
            full_name=full_name,
            email=text["email"],
            phone=text["phone"],
            telegram=None if values["telegram"] is None else normalize_telegram(import_file_service.to_text(values["telegram"])),
            position=text["position"],
            channels=None if values["channels"] is None else import_file_service.to_contact_channels(values["channels"]),
        )

    def import_contact(self, organization: Organization, contact_row: ContactRow) -> ContactImportResult:
        """Находит или создаёт человека и его связь с организацией, записывает данные строки."""
        match = contact_matching_service.match_for_import(
            organization=organization,
            full_name=contact_row.full_name,
            email=contact_row.email or "",
            phone=contact_row.phone or "",
            telegram=contact_row.telegram or "",
        )
        warnings: list[str] = []
        contact = match.contact
        if contact is None:
            contact = ContactPerson.objects.create(
                full_name=contact_row.full_name,
                email=contact_row.email or "",
                phone=contact_row.phone or "",
                telegram=contact_row.telegram or "",
            )
            if match.possible_duplicates:
                similar = ", ".join(
                    f"{duplicate.full_name} ({duplicate.email or duplicate.phone or 'без контактов'})"
                    for duplicate in match.possible_duplicates
                )
                warnings.append(f"контактное лицо {contact.full_name} создано новым человеком, похожие: {similar}")
        else:
            self._update_person(contact=contact, contact_row=contact_row)

        affiliation, created = contact_affiliation_service.get_or_create(contact=contact, organization=organization)
        # Человек есть в файле организации — значит, работает: выключенный включается.
        contact_affiliation_service.activate_contact(contact=contact)
        updates = {}
        if contact_row.position is not None:
            updates["position"] = contact_row.position
        if contact_row.channels is not None:
            updates["preferred_channels"] = contact_row.channels
        self._save(instance=affiliation, values=updates)
        return ContactImportResult(affiliation=affiliation, created=created, warnings=warnings)

    def _update_person(self, contact: ContactPerson, contact_row: ContactRow) -> None:
        """Заполненные контактные данные строки перезаписывают данные человека, пустые — не стирают."""
        updates = {
            field: value
            for field, value in (
                ("email", contact_row.email),
                ("phone", contact_row.phone),
                ("telegram", contact_row.telegram),
            )
            if value
        }
        if text_key(contact.full_name) == text_key(contact_row.full_name):
            updates["full_name"] = contact_row.full_name
        self._save(instance=contact, values=updates)

    def _save(self, instance, values: dict) -> None:
        """Записывает изменённые значения и сохраняет только эти поля."""
        changed = {field: value for field, value in values.items() if getattr(instance, field) != value}
        if not changed:
            return
        for field, value in changed.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*changed, "updated_at"])


contact_import_service = ContactImportService()
