from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction

from sova.catalog.exceptions import CatalogImportError
from sova.catalog.models import ContactPerson
from sova.catalog.schemas import ImportRowWarning
from sova.catalog.services.catalog_lookup import catalog_lookup_service
from sova.catalog.services.import_file import Rows, import_file_service
from sova.core.text import text_key
from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError
from sova.interactions.models import Contract, InteractionDirection, InteractionProduct, InteractionProgram
from sova.interactions.services import license_service, responsible_service

_MANAGER_FIELD = "draft_manager_full_name"
_DRAFT_FIELDS = (_MANAGER_FIELD, "draft_status", "draft_comment")


@dataclass
class _ContractGroup:
    """Строки одного договора в файле: итоговые черновые поля и договор, найденный или созданный по ним."""

    first_row: int
    drafts: dict[str, str]
    # Строка, из которой взято ФИО менеджера, — для предупреждения «менеджер не найден».
    manager_row: int
    contract: Contract | None = None


class ContractRegistryImportService:
    """
    Импорт реестра договоров: headless `Contract` (без Interaction) с продуктами, лицензиями,
    направлениями/программами и ответственными от вуза.

    Строки группируются по договору (вуз + contract_number без учёта регистра): несколько строк одного
    договора — несколько продуктов. Привязка договора к Interaction — отдельно, в `ContractAttachmentService`.

    Черновые поля (менеджер, статус, комментарий) — одно значение на договор, поэтому собираются по всем
    строкам договора до записи: значение берётся из любой заполненной строки; колонка есть, но пуста во
    всех строках договора — значение стирается; колонки нет — поле не меняется; разные непустые значения
    в строках одного договора — ошибка строки.

    «ФИО Менеджера» ответственным не назначается: оно хранится в договоре и при создании взаимодействия
    служит подсказкой для явного выбора ответственного. Если по ФИО не находится ровно один пользователь,
    в результат импорта добавляется предупреждение.
    """

    @transaction.atomic
    def import_rows(self, rows: Rows, warnings: list[ImportRowWarning] | None = None) -> tuple[int, int]:
        """
        Апсертит headless Contract + продукты/лицензии по строкам с каноническими ключами.

        Весь файл — одна транзакция: ошибки собираются по всем строкам (`CatalogImportRowsError`),
        и при любой ошибке импорт откатывается целиком. Возвращает (создано договоров, обновлено договоров);
        предупреждения (менеджер не найден) добавляются в `warnings`, если список передан.
        """
        rows = list(rows)
        groups = self._collect_groups(rows=rows)
        created_ids: set = set()
        updated_ids: set = set()

        def _handle_row(row: dict) -> None:
            contract, was_created = self._process_row(row=row, groups=groups, touched_ids=created_ids | updated_ids)
            if contract.pk not in created_ids and contract.pk not in updated_ids:
                (created_ids if was_created else updated_ids).add(contract.pk)

        import_file_service.process_rows(rows=iter(rows), handler=_handle_row)
        manager_warnings = self._check_managers(groups=groups.values())
        if warnings is not None:
            warnings.extend(manager_warnings)
        return len(created_ids), len(updated_ids)

    def _collect_groups(self, rows: list[tuple[int, dict]]) -> dict[tuple, _ContractGroup]:
        """
        Итоговые черновые поля каждого договора файла: {(вуз, номер): группа строк договора}.

        В значения попадают только колонки, которые есть в файле: первое непустое значение из строк договора,
        иначе пустая строка (значение будет стёрто). Строки с ошибкой вуза или номера пропускаются — их
        ошибки сообщит основной проход.
        """
        present = [name for name in _DRAFT_FIELDS if rows and name in rows[0][1]]
        groups: dict[tuple, _ContractGroup] = {}
        for row_number, row in rows:
            try:
                key = self._contract_key(row=row)
            except (CatalogImportError, KeyError):
                continue
            group = groups.setdefault(
                key, _ContractGroup(first_row=row_number, drafts=dict.fromkeys(present, ""), manager_row=row_number)
            )
            for name in present:
                if not group.drafts[name]:
                    group.drafts[name] = import_file_service.to_text(row.get(name))
                    if name == _MANAGER_FIELD and group.drafts[name]:
                        group.manager_row = row_number
        return groups

    def _check_managers(self, groups) -> list[ImportRowWarning]:
        """
        Предупреждения о менеджерах, которых нельзя будет предложить ответственными.

        Менеджер из файла никуда не назначается: ФИО хранится в договоре, а при создании взаимодействия
        по нему подбирается подсказка (`ResponsibleService.suggest_manager`). Если пользователя с таким
        ФИО нет или их несколько, об этом лучше узнать сразу при загрузке.
        """
        warnings: list[ImportRowWarning] = []
        users = list(get_user_model().objects.filter(is_active=True))
        for group in groups:
            full_name = group.drafts.get(_MANAGER_FIELD)
            if group.contract is None or not full_name:
                continue
            try:
                responsible_service.find_manager(full_name=full_name, users=users)
            except ManagerNotFoundError:
                reason = "нет пользователя с таким ФИО"
            except AmbiguousManagerError:
                reason = "несколько пользователей с таким ФИО"
            else:
                continue
            warnings.append(
                ImportRowWarning(
                    row_number=group.manager_row,
                    message=(
                        f"менеджер {full_name} договора {group.contract.contract_number} не будет предложен "
                        f"ответственным: {reason}"
                    ),
                )
            )
        return warnings

    def _contract_key(self, row: dict) -> tuple:
        """Ключ договора в файле: найденный вуз + номер без учёта регистра (как поиск договора в БД)."""
        university = catalog_lookup_service.find_university(raw_value=row["university"])
        contract_number = import_file_service.to_text(row["contract_number"])
        if not contract_number:
            raise CatalogImportError("поле contract_number обязательно")
        return university.pk, text_key(contract_number)

    def _process_row(self, row: dict, groups: dict[tuple, _ContractGroup], touched_ids: set) -> tuple[Contract, bool]:
        """Апсертит договор одной строки и добавляет к нему продукт, лицензию и ответственных."""
        university = catalog_lookup_service.find_university(raw_value=row["university"])
        vendor = catalog_lookup_service.find_vendor(raw_value=row.get("vendor"))
        product = catalog_lookup_service.find_product(raw_value=row["product"], vendor=vendor)

        contract_number = import_file_service.to_text(row["contract_number"])
        if not contract_number:
            raise CatalogImportError("поле contract_number обязательно")

        group = groups[(university.pk, text_key(contract_number))]
        drafts = group.drafts
        self._check_no_conflict(row=row, contract_number=contract_number, drafts=drafts)

        # Явный filter+create вместо get_or_create: interaction__isnull и contract_number__iexact — лукапы,
        # а не поля модели, их нельзя передать как параметры создания. Номер сравнивается без учёта регистра.
        contract = Contract.objects.filter(
            contract_number__iexact=contract_number, university=university, interaction__isnull=True
        ).first()
        was_created = contract is None
        if was_created:
            contract = Contract.objects.create(contract_number=contract_number, university=university, **drafts)
        elif contract.pk not in touched_ids:
            # Черновые поля договора записываются один раз — итоговыми значениями по всем его строкам.
            for field, value in drafts.items():
                setattr(contract, field, value)
            contract.save(update_fields=[*drafts, "updated_at"])
        group.contract = contract

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

    def _check_no_conflict(self, row: dict, contract_number: str, drafts: dict[str, str]) -> None:
        """Непустое черновое поле строки должно совпадать со значением договора из первой заполненной строки."""
        conflicts = [
            field
            for field, value in drafts.items()
            if (row_value := import_file_service.to_text(row.get(field))) and row_value != value
        ]
        if conflicts:
            raise CatalogImportError(
                f"расходятся значения внутри группы договора {contract_number}: {', '.join(conflicts)}"
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
