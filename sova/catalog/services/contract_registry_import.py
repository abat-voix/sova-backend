from django.db import transaction

from sova.catalog.exceptions import CatalogImportError
from sova.catalog.models import ContactPerson
from sova.catalog.services.catalog_lookup import catalog_lookup_service
from sova.catalog.services.import_file import Rows, import_file_service
from sova.interactions.models import Contract, InteractionDirection, InteractionProduct, InteractionProgram
from sova.interactions.services import license_service

_DRAFT_FIELDS = ("draft_manager_full_name", "draft_status", "draft_comment")


class ContractRegistryImportService:
    """
    Импорт реестра договоров: headless `Contract` (без Interaction) с продуктами, лицензиями,
    направлениями/программами и ответственными от вуза.

    Строки группируются по contract_number: несколько строк одного договора — несколько продуктов.
    Привязка договора к Interaction — отдельно, в `ContractAttachmentService`.
    """

    @transaction.atomic
    def import_rows(self, rows: Rows) -> tuple[int, int]:
        """
        Апсертит headless Contract + продукты/лицензии по строкам с каноническими ключами.

        Весь файл — одна транзакция: ошибки собираются по всем строкам (`CatalogImportRowsError`),
        и при любой ошибке импорт откатывается целиком. Возвращает (создано договоров, обновлено договоров).
        """
        created_ids: set = set()
        updated_ids: set = set()

        def _handle_row(row: dict) -> None:
            contract, was_created = self._process_row(row=row, touched_ids=created_ids | updated_ids)
            if contract.pk not in created_ids and contract.pk not in updated_ids:
                (created_ids if was_created else updated_ids).add(contract.pk)

        import_file_service.process_rows(rows=rows, handler=_handle_row)
        return len(created_ids), len(updated_ids)

    def _process_row(self, row: dict, touched_ids: set) -> tuple[Contract, bool]:
        """Апсертит договор одной строки и добавляет к нему продукт, лицензию и ответственных."""
        university = catalog_lookup_service.find_university(raw_value=row["university"])
        vendor = catalog_lookup_service.find_vendor(raw_value=row.get("vendor"))
        product = catalog_lookup_service.find_product(raw_value=row["product"], vendor=vendor)

        contract_number = import_file_service.to_text(row["contract_number"])
        if not contract_number:
            raise CatalogImportError("поле contract_number обязательно")

        drafts = {field: import_file_service.to_text(row.get(field)) for field in _DRAFT_FIELDS}

        # Явный filter+create вместо get_or_create: interaction__isnull и contract_number__iexact — лукапы,
        # а не поля модели, их нельзя передать как параметры создания. Номер сравнивается без учёта регистра.
        contract = Contract.objects.filter(
            contract_number__iexact=contract_number, university=university, interaction__isnull=True
        ).first()
        was_created = contract is None
        if was_created:
            contract = Contract.objects.create(contract_number=contract_number, university=university, **drafts)
        else:
            # Расхождение внутри группы строк текущего файла — ошибка; повторный импорт перезаписывает.
            if contract.pk in touched_ids:
                self._check_no_conflict(contract=contract, drafts=drafts)
            changed = {field: value for field, value in drafts.items() if value}
            for field, value in changed.items():
                setattr(contract, field, value)
            contract.save(update_fields=[*changed, "updated_at"])

        interaction_program = self._resolve_program(row=row, contract=contract)

        item, _ = InteractionProduct.objects.get_or_create(
            contract=contract,
            product=product,
            defaults={"interaction_program": interaction_program},
        )

        # Колонка «лицензия подписана» содержит либо дату подписания, либо да/нет.
        signed_at = import_file_service.to_date(row.get("license_signed"))
        license_service.create_license(
            contract=contract,
            interaction_product=item,
            signed_at=signed_at,
            valid_until_year=import_file_service.to_year(row.get("license_valid_until_year")),
            is_signed=signed_at is not None or import_file_service.is_true(row.get("license_signed")),
            created_by=None,
        )

        for full_name in import_file_service.split_list(row.get("university_contact")):
            # Ответственный из реестра только дополняет справочник: найденная запись не переименовывается.
            if not ContactPerson.objects.filter(university=university, full_name__iexact=full_name).exists():
                ContactPerson.objects.create(university=university, full_name=full_name)

        return contract, was_created

    def _check_no_conflict(self, contract: Contract, drafts: dict[str, str]) -> None:
        """Черновые поля в строках одного договора внутри файла не должны противоречить друг другу."""
        conflicts = [
            field
            for field, value in drafts.items()
            if value and getattr(contract, field) and value != getattr(contract, field)
        ]
        if conflicts:
            raise CatalogImportError(
                "расходятся значения внутри группы договора "
                f"{contract.contract_number}: {', '.join(conflicts)}"
            )

    def _resolve_program(self, row: dict, contract: Contract) -> InteractionProgram | None:
        """Создаёт направление/программу договора; направление выводится из программы, если не указано."""
        program_name = import_file_service.to_text(row.get("program"))
        direction_name = import_file_service.to_text(row.get("direction"))
        if not program_name and not direction_name:
            return None

        direction = None
        if direction_name:
            direction = catalog_lookup_service.find_direction(raw_value=direction_name)

        program = None
        if program_name:
            program = catalog_lookup_service.find_program(name=program_name)
            if direction is not None and program.direction_id != direction.id:
                raise CatalogImportError(
                    f"программа {program_name} принадлежит другому направлению, "
                    f"чем указанное {direction_name}"
                )
            direction = program.direction

        InteractionDirection.objects.get_or_create(contract=contract, direction=direction)

        if program is None:
            return None

        interaction_program, _ = InteractionProgram.objects.get_or_create(contract=contract, program=program)
        return interaction_program


contract_registry_import_service = ContractRegistryImportService()
