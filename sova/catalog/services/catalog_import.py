from collections.abc import Callable

from django.contrib.auth.models import AbstractBaseUser
from django.db import models, transaction

from sova.catalog.enum import CatalogType
from sova.catalog.models import ContactPerson, Direction, Product, Program, University, Vendor
from sova.catalog.models.university import InstitutionType
from sova.catalog.schemas import CATALOG_IMPORT_FIELDS, CatalogImportResult, ImportRowWarning
from sova.catalog.services.catalog_lookup import catalog_lookup_service
from sova.catalog.services.contract_registry_import import contract_registry_import_service
from sova.catalog.services.import_file import ImportSource, Rows, import_file_service


class CatalogImportService:
    """
    Импорт каталогов из xlsx: вузы, вендоры, направления, программы, продукты, ответственные от вуза.

    Точка входа для любого catalog_type, включая реестр договоров (его обрабатывает
    `ContractRegistryImportService`). Простой каталог: одна строка — одна запись, апсерт по
    external_code/name. Для всех типов весь файл — одна транзакция: ошибки собираются по всем
    строкам (`CatalogImportRowsError`), и при любой ошибке импорт откатывается целиком.

    Файл — источник истины только для своих колонок: колонки нет — поле найденной записи не меняется,
    ячейка пуста — значение стирается. Исключение — external_code: пустая ячейка не стирает код,
    по которому запись находится при следующих загрузках. Записи, которых нет в файле, не меняются.
    """

    def import_file(
        self,
        catalog_type: str,
        source: ImportSource,
        user: AbstractBaseUser | None = None,
    ) -> CatalogImportResult:
        """
        Импорт файла с произвольными заголовками, переведёнными через CatalogImportMapping.

        `user` — загрузивший файл; реестр договоров записывает его автором назначений КАМов.
        """
        rows = import_file_service.read_mapped_rows(
            catalog_type=catalog_type,
            source=source,
            required=CATALOG_IMPORT_FIELDS[catalog_type].required,
        )
        return self._run_loader(catalog_type=catalog_type, rows=rows, user=user)

    def import_canonical_file(self, catalog_type: str, source: ImportSource) -> CatalogImportResult:
        """Импорт файла, заголовки которого уже совпадают с каноническими ключами (CLI loaddata)."""
        rows = import_file_service.read_canonical_rows(source=source, required=CATALOG_IMPORT_FIELDS[catalog_type].required)
        return self._run_loader(catalog_type=catalog_type, rows=rows)

    @transaction.atomic
    def load_universities(self, rows: Rows) -> tuple[int, int]:
        """Вузы: апсерт по ror (или id), иначе по name."""
        return self._count(import_file_service.process_rows(rows=rows, handler=self._load_university))

    @transaction.atomic
    def load_vendors(self, rows: Rows) -> tuple[int, int]:
        """Вендоры: апсерт по external_code, иначе по name."""
        return self._count(
            import_file_service.process_rows(rows=rows, handler=lambda row: self._load_simple_named(row=row, model=Vendor))
        )

    @transaction.atomic
    def load_directions(self, rows: Rows) -> tuple[int, int]:
        """Направления: апсерт по external_code, иначе по name."""
        return self._count(
            import_file_service.process_rows(rows=rows, handler=lambda row: self._load_simple_named(row=row, model=Direction))
        )

    @transaction.atomic
    def load_programs(self, rows: Rows) -> tuple[int, int]:
        """Программы: апсерт по паре name+direction."""
        return self._count(import_file_service.process_rows(rows=rows, handler=self._load_program))

    @transaction.atomic
    def load_products(self, rows: Rows) -> tuple[int, int]:
        """Продукты: апсерт по external_code, иначе по name в пределах вендора; связь с программами."""
        return self._count(import_file_service.process_rows(rows=rows, handler=self._load_product))

    @transaction.atomic
    def load_contact_persons(self, rows: Rows) -> tuple[int, int]:
        """Ответственные от вуза: апсерт по паре university+full_name."""
        return self._count(import_file_service.process_rows(rows=rows, handler=self._load_contact_person))

    def _run_loader(
        self, catalog_type: str, rows: Rows, user: AbstractBaseUser | None = None
    ) -> CatalogImportResult:
        """Загружает строки обработчиком типа; предупреждения строк сейчас бывают только у реестра договоров."""
        warnings: list[ImportRowWarning] = []
        loader = self._get_loader(catalog_type=catalog_type, warnings=warnings, user=user)
        created, updated = loader(rows)
        return CatalogImportResult(created=created, updated=updated, warnings=warnings)

    def _get_loader(
        self, catalog_type: str, warnings: list[ImportRowWarning], user: AbstractBaseUser | None = None
    ) -> Callable[[Rows], tuple[int, int]]:
        """Обработчик строк для catalog_type; реестр договоров группирует строки по номеру договора."""
        return {
            CatalogType.UNIVERSITY: self.load_universities,
            CatalogType.VENDOR: self.load_vendors,
            CatalogType.DIRECTION: self.load_directions,
            CatalogType.PROGRAM: self.load_programs,
            CatalogType.PRODUCT: self.load_products,
            CatalogType.CONTACT_PERSON: self.load_contact_persons,
            CatalogType.CONTRACT_REGISTRY: lambda rows: contract_registry_import_service.import_rows(
                rows=rows, warnings=warnings, user=user
            ),
        }[catalog_type]

    def _count(self, results: list[bool]) -> tuple[int, int]:
        """(создано, обновлено) по результатам строк: True — запись создана, False — обновлена."""
        created = sum(results)
        return created, len(results) - created

    def _load_university(self, row: dict) -> bool:
        """Апсерт вуза из строки; True — создан."""
        name = import_file_service.to_text(row["name"])
        if not name:
            raise ValueError("поле name обязательно")

        external_code = import_file_service.to_text(row["ror"]) or import_file_service.to_text(row["id"])
        if not external_code:
            raise ValueError("должно быть заполнено поле ror или id")

        allowed_types = {value for value, _label in InstitutionType.choices}
        institution_type = import_file_service.to_text(row["type"]).lower() or InstitutionType.EDUCATION
        if institution_type not in allowed_types:
            raise ValueError(f"неизвестный type: {institution_type}")

        defaults = {
            "name": name,
            "name_en": import_file_service.to_text(row["name_en"]),
            "short_name": import_file_service.to_text(row["short_name"]),
            "institution_type": institution_type,
            "country_code": import_file_service.to_text(row["country_code"]).upper(),
            "region": import_file_service.to_text(row["region"]),
            "city": import_file_service.to_text(row["city"]),
            "lat": import_file_service.to_decimal(row["lat"]),
            "lon": import_file_service.to_decimal(row["lon"]),
            "works_count": import_file_service.to_positive_int(row["works_count"]),
            "cited_by_count": import_file_service.to_positive_int(row["cited_by_count"]),
            "homepage_url": import_file_service.to_text(row["homepage_url"]),
        }
        _, was_created = self._upsert(model=University, external_code=external_code, name=name, defaults=defaults)
        return was_created

    def _load_simple_named(self, row: dict, model: type[models.Model]) -> bool:
        """Апсерт справочника из name/external_code/is_active; True — создан."""
        name = import_file_service.to_text(row.get("name"))
        if not name:
            raise ValueError("поле name обязательно")
        external_code = import_file_service.to_text(row.get("external_code")) or None
        defaults = {"name": name, **self._is_active(row=row)}

        _, was_created = self._upsert(model=model, external_code=external_code, name=name, defaults=defaults)
        return was_created

    def _load_program(self, row: dict) -> bool:
        """Апсерт программы из строки; True — создана."""
        name = import_file_service.to_text(row["name"])
        if not name:
            raise ValueError("поле name обязательно")
        direction = catalog_lookup_service.find_direction(raw_value=row["direction"])
        defaults = {"name": name, "direction": direction, **self._is_active(row=row)}

        # У Program нет external_code, поэтому апсерт идёт по паре name+direction
        # (аналогично name+vendor у Product).
        program = Program.objects.filter(name__iexact=name, direction=direction).first()
        if program is None:
            Program.objects.create(**defaults)
            return True

        self._update(instance=program, values=defaults)
        return False

    def _load_product(self, row: dict) -> bool:
        """Апсерт продукта и его связей с программами из строки; True — создан."""
        name = import_file_service.to_text(row["name"])
        if not name:
            raise ValueError("поле name обязательно")
        external_code = import_file_service.to_text(row["external_code"]) or None
        vendor = catalog_lookup_service.find_vendor(raw_value=row["vendor"])
        defaults = {"name": name, "vendor": vendor, **self._is_active(row=row)}

        # Уникальность продукта — в паре с вендором (или одна, если вендора нет), поэтому
        # апсерт по имени ищет среди продуктов того же вендора, а не по всему справочнику.
        product = None
        if external_code:
            product = Product.objects.filter(external_code__iexact=external_code).first()
        if product is None:
            product = Product.objects.filter(name__iexact=name, vendor=vendor).first()

        was_created = product is None
        if was_created:
            product = Product.objects.create(external_code=external_code, **defaults)
        else:
            self._update(instance=product, values=self._with_code(defaults=defaults, external_code=external_code))

        # Колонка programs необязательна: если её нет в файле — существующие связи не трогаем,
        # если есть (пусть и пустая) — приводим M2M к тому, что в ней перечислено.
        if "programs" in row:
            product.programs.set(catalog_lookup_service.find_programs(raw_value=row["programs"]))

        return was_created

    def _load_contact_person(self, row: dict) -> bool:
        """Апсерт ответственного от вуза из строки; True — создан."""
        full_name = import_file_service.to_text(row["full_name"])
        if not full_name:
            raise ValueError("поле full_name обязательно")
        university = catalog_lookup_service.find_university(raw_value=row["university"])
        defaults = {
            field: import_file_service.to_text(row[field]) for field in ("position", "email", "phone") if field in row
        }

        # ФИО сравнивается без учёта регистра, написание из файла перезаписывает сохранённое.
        contact = ContactPerson.objects.filter(university=university, full_name__iexact=full_name).first()
        if contact is None:
            ContactPerson.objects.create(university=university, full_name=full_name, **defaults)
            return True

        self._update(instance=contact, values={"full_name": full_name, **defaults})
        return False

    def _upsert(
        self,
        model: type[models.Model],
        external_code: str | None,
        name: str,
        defaults: dict,
    ) -> tuple[models.Model, bool]:
        """Апсерт справочника по external_code (если задан), иначе по name."""
        instance = None
        if external_code:
            instance = model.objects.filter(external_code__iexact=external_code).first()
        if instance is None:
            instance = model.objects.filter(name__iexact=name).first()

        if instance is None:
            return model.objects.create(external_code=external_code, **defaults), True

        self._update(instance=instance, values=self._with_code(defaults=defaults, external_code=external_code))
        return instance, False

    def _is_active(self, row: dict) -> dict:
        """{is_active: значение}, если колонка есть в файле; иначе пусто — поле не меняется (у новой записи — True)."""
        if "is_active" not in row:
            return {}
        return {"is_active": import_file_service.to_bool(row["is_active"])}

    def _with_code(self, defaults: dict, external_code: str | None) -> dict:
        """Поля обновления найденной записи: пустой код из файла не стирает сохранённый."""
        return {**defaults, "external_code": external_code} if external_code else defaults

    def _update(self, instance: models.Model, values: dict) -> None:
        """Записывает значения в найденную запись и сохраняет только эти поля."""
        for field, value in values.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*values, "updated_at"])


catalog_import_service = CatalogImportService()
