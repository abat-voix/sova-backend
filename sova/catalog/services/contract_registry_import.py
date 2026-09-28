from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from accounts.models import SystemRole
from sova.catalog.exceptions import CatalogImportError
from sova.catalog.schemas import ImportRowWarning
from sova.catalog.services.catalog_lookup import catalog_lookup_service
from sova.catalog.services.contact_affiliation import contact_affiliation_service
from sova.catalog.services.import_file import Rows, import_file_service
from sova.core.text import text_key
from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError
from sova.interactions.models import Contract, InteractionDirection, InteractionProduct, InteractionProgram
# Модули, а не пакет sova.interactions.services: пакет импортирует сервис связей каталога (цикл импорта).
from sova.interactions.services.license import license_service
from sova.interactions.services.responsible import responsible_service

_MANAGER_FIELD = "manager_full_name"
_DRAFT_FIELDS = ("draft_status", "draft_comment")


@dataclass
class _ContractGroup:
    """Строки одного договора в файле: итоговые черновые поля, ФИО менеджеров и договор, найденный или созданный по ним."""

    first_row: int
    contract_number: str
    drafts: dict[str, str]
    # Договор уже привязан к взаимодействию: его строки не загружаются.
    attached: bool = False
    # ФИО менеджеров договора без учёта регистра → (ФИО как в файле, строка первого появления — для предупреждения).
    manager_names: dict[str, tuple[str, int]] = field(default_factory=dict)
    contract: Contract | None = None


class ContractRegistryImportService:
    """
    Импорт реестра договоров: headless `Contract` (без Interaction) с продуктами, лицензиями,
    направлениями/программами и ответственными от организации.

    Строки группируются по договору (организация + contract_number без учёта регистра): несколько строк одного
    договора — несколько продуктов. Привязка договора к Interaction — отдельно, в `ContractAttachmentService`.
    Реестр нужен только для создания взаимодействий: строки договора, уже привязанного к взаимодействию, не
    загружаются (договор не меняется и не дублируется) — предупреждение в результате импорта.

    Черновые поля (статус, комментарий) — одно значение на договор, поэтому собираются по всем
    строкам договора до записи: значение берётся из любой заполненной строки; колонка есть, но пуста во
    всех строках договора — значение стирается; колонки нет — поле не меняется; разные непустые значения
    в строках одного договора — ошибка строки.

    «ФИО Менеджера» — по одному в строке; КАМы договора — все ФИО его строк. ФИО ищется среди активных КАМов;
    найденные назначаются ответственными договора (`Responsible` без взаимодействия) от имени загрузившего файл.
    На взаимодействие, созданное из договора, они не переходят — это подсказка для назначения ответственных. Файл — источник правды: при повторной загрузке
    КАМы, которых в файле больше нет или чьё ФИО не распознано, снимаются. Колонки нет — ответственные не
    меняются. Не нашёлся ровно один КАМ — предупреждение в результате импорта.
    """

    @transaction.atomic
    def import_rows(
        self,
        rows: Rows,
        warnings: list[ImportRowWarning] | None = None,
        user: AbstractBaseUser | None = None,
    ) -> tuple[int, int]:
        """
        Апсертит headless Contract + продукты/лицензии по строкам с каноническими ключами и назначает КАМов договора.

        Весь файл — одна транзакция: ошибки собираются по всем строкам (`CatalogImportRowsError`),
        и при любой ошибке импорт откатывается целиком. Возвращает (создано договоров, обновлено договоров);
        предупреждения (менеджер не найден) добавляются в `warnings`, если список передан. `user` — загрузивший
        файл, автор назначений.
        """
        rows = list(rows)
        groups = self._collect_groups(rows=rows)
        created_ids: set = set()
        updated_ids: set = set()

        def _handle_row(row: dict) -> None:
            contract, was_created = self._process_row(row=row, groups=groups, touched_ids=created_ids | updated_ids)
            if contract is None:
                return
            if contract.pk not in created_ids and contract.pk not in updated_ids:
                (created_ids if was_created else updated_ids).add(contract.pk)

        import_file_service.process_rows(rows=iter(rows), handler=_handle_row)
        result_warnings = [
            ImportRowWarning(
                row_number=group.first_row,
                message=f"договор {group.contract_number} уже привязан к взаимодействию, его строки не загружены",
            )
            for group in groups.values()
            if group.attached
        ]
        if rows and _MANAGER_FIELD in rows[0][1]:
            result_warnings.extend(self._sync_managers(groups=groups.values(), assigned_by=user))
        if warnings is not None:
            warnings.extend(result_warnings)
        return len(created_ids), len(updated_ids)

    def _collect_groups(self, rows: list[tuple[int, dict]]) -> dict[tuple, _ContractGroup]:
        """
        Итоговые черновые поля и ФИО менеджеров каждого договора файла: {(организация, номер): группа строк договора}.

        Группа договора, уже привязанного к взаимодействию, помечается `attached` — её строки не загружаются.

        В значения попадают только колонки, которые есть в файле: первое непустое значение из строк договора,
        иначе пустая строка (значение будет стёрто). ФИО менеджеров собираются по всем строкам договора. Строки с ошибкой организации или номера пропускаются — их
        ошибки сообщит основной проход.
        """
        present = [name for name in _DRAFT_FIELDS if rows and name in rows[0][1]]
        groups: dict[tuple, _ContractGroup] = {}
        for row_number, row in rows:
            try:
                key = self._contract_key(row=row)
            except (CatalogImportError, KeyError):
                continue
            if key not in groups:
                contract_number = import_file_service.to_text(row["contract_number"])
                groups[key] = _ContractGroup(
                    first_row=row_number,
                    contract_number=contract_number,
                    drafts=dict.fromkeys(present, ""),
                    attached=Contract.objects.filter(
                        organization_id=key[0], contract_number__iexact=contract_number, interaction__isnull=False
                    ).exists(),
                )
            group = groups[key]
            for name in present:
                if not group.drafts[name]:
                    group.drafts[name] = import_file_service.to_text(row.get(name))
            manager_name = import_file_service.to_text(row.get(_MANAGER_FIELD))
            if manager_name:
                group.manager_names.setdefault(text_key(manager_name), (manager_name, row_number))
        return groups

    def _sync_managers(self, groups, assigned_by: AbstractBaseUser | None) -> list[ImportRowWarning]:
        """
        Назначает договорам КАМов из «ФИО Менеджера» и снимает тех, кого в файле нет.

        ФИО ищется среди активных КАМов (роль `kam`); не нашёлся ровно один — предупреждение на строку, где ФИО
        встретилось впервые, и КАМ этому ФИО не назначается.
        """
        warnings: list[ImportRowWarning] = []
        kams = list(get_user_model().objects.filter(is_active=True, system_role__role=SystemRole.KAM))
        for group in groups:
            if group.contract is None:
                continue
            managers = []
            for full_name, row_number in group.manager_names.values():
                try:
                    managers.append(responsible_service.find_manager(full_name=full_name, users=kams))
                except ManagerNotFoundError:
                    reason = "нет КАМа с таким ФИО"
                except AmbiguousManagerError:
                    reason = "несколько КАМов с таким ФИО"
                else:
                    continue
                warnings.append(
                    ImportRowWarning(
                        row_number=row_number,
                        message=f"менеджер {full_name} договора {group.contract.contract_number} не назначен: {reason}",
                    )
                )
            responsible_service.sync_contract_responsibles(
                contract=group.contract, managers=managers, assigned_by=assigned_by
            )
        return warnings

    def _contract_key(self, row: dict) -> tuple:
        """Ключ договора в файле: найденная организация + номер без учёта регистра (как поиск договора в БД)."""
        organization = catalog_lookup_service.find_organization(raw_value=row["organization"])
        contract_number = import_file_service.to_text(row["contract_number"])
        if not contract_number:
            raise CatalogImportError("поле contract_number обязательно")
        return organization.pk, text_key(contract_number)

    def _process_row(
        self, row: dict, groups: dict[tuple, _ContractGroup], touched_ids: set
    ) -> tuple[Contract | None, bool]:
        """
        Апсертит договор одной строки и добавляет к нему продукт, лицензию и ответственных.

        Строку договора, уже привязанного к взаимодействию, пропускает без проверок — (None, False).
        """
        organization = catalog_lookup_service.find_organization(raw_value=row["organization"])
        contract_number = import_file_service.to_text(row["contract_number"])
        if not contract_number:
            raise CatalogImportError("поле contract_number обязательно")

        group = groups[(organization.pk, text_key(contract_number))]
        if group.attached:
            return None, False

        vendor = catalog_lookup_service.find_vendor(raw_value=row.get("vendor"))
        product = catalog_lookup_service.find_product(raw_value=row["product"], vendor=vendor)
        drafts = group.drafts
        self._check_no_conflict(row=row, contract_number=contract_number, drafts=drafts)

        # Явный filter+create вместо get_or_create: interaction__isnull и contract_number__iexact — лукапы,
        # а не поля модели, их нельзя передать как параметры создания. Номер сравнивается без учёта регистра.
        # Блокировка: параллельная привязка договора (она тоже блокирует строку) дождётся конца импорта и не
        # привяжет договор посреди его обновления.
        contract = Contract.objects.select_for_update().filter(
            contract_number__iexact=contract_number, organization=organization, interaction__isnull=True
        ).first()
        was_created = contract is None
        if was_created:
            contract = Contract.objects.create(contract_number=contract_number, organization=organization, **drafts)
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

        for full_name in import_file_service.split_list(row.get("organization_contact")):
            self._add_organization_contact(organization=organization, full_name=full_name)

        return contract, was_created

    def _add_organization_contact(self, organization, full_name: str) -> None:
        """
        Ответственный от организации из реестра только дополняет справочник: найденный человек не меняется.

        Тёзка у организации есть (один или несколько) — ничего не создаётся: реестр не про контакты, и без email/телефона
        выбрать среди тёзок нельзя.
        """
        if contact_affiliation_service.contacts_for(organization=organization).filter(full_name__iexact=full_name).exists():
            return
        contact_affiliation_service.create_contact(organization=organization, full_name=full_name)

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
