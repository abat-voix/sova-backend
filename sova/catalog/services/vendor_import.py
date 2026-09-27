from django.db import transaction

from sova.catalog.exceptions import CatalogImportError
from sova.catalog.models import Product, Vendor, VendorContact
from sova.catalog.schemas import ImportRowWarning
from sova.catalog.services.contact_affiliation import contact_affiliation_service
from sova.catalog.services.contact_import import contact_import_service
from sova.catalog.services.import_file import Rows, import_file_service
from sova.core.text import normalize_quotes, quote_insensitive_key


class VendorImportService:
    """
    Импорт вендоров: справочник (name, external_code, is_active) или файл «вендор + продукты + контактное лицо».

    Строка файла Вендоры.xlsx — вендор, его продукты через «,»/«;» и одно контактное лицо, отвечающее за эти
    продукты; вендор может повторяться в нескольких строках. Кавычки не записываются как есть: у продукта снимается
    внешняя пара («Базис Dynamix» → Базис Dynamix), кавычки в названиях приводятся к «ёлочкам»
    (ООО "Базис" → ООО «Базис»). Вендор и продукт находятся без учёта регистра и вида кавычек.

    Продукты из файла только добавляются: продукты вендора, которых в файле нет, не меняются. Найденный продукт без
    вендора получает вендора из файла; продукт с таким названием у другого вендора — новый продукт + предупреждение.
    Продукты контакта (`VendorContact.products`) — объединение продуктов всех его строк у этого вендора; колонок
    продуктов или ФИО нет в файле — продукты контактов не меняются.
    """

    @transaction.atomic
    def import_rows(self, rows: Rows, warnings: list[ImportRowWarning] | None = None) -> tuple[int, int]:
        """
        Загружает строки с каноническими ключами; возвращает (создано вендоров, обновлено вендоров).

        Весь файл — одна транзакция, ошибки собираются по всем строкам. Предупреждения — в `warnings`.
        """
        rows = list(rows)
        columns = set(rows[0][1]) if rows else set()
        created_ids: set = set()
        updated_ids: set = set()
        # Связь контакта с вендором → продукты из всех его строк.
        contact_products: dict[VendorContact, dict] = {}
        row_warnings: list[ImportRowWarning] = []

        def _handle_row(row_number: int, row: dict) -> None:
            vendor, was_created = self._upsert_vendor(row=row, touched=created_ids | updated_ids)
            if vendor.pk not in created_ids | updated_ids:
                (created_ids if was_created else updated_ids).add(vendor.pk)

            products = []
            if "products" in row:
                products, messages = self._resolve_products(vendor=vendor, raw_value=row["products"])
                row_warnings.extend(ImportRowWarning(row_number=row_number, message=message) for message in messages)

            contact_row = contact_import_service.parse(row=row, prefix="contact_")
            if contact_row is None:
                return
            result = contact_import_service.import_contact(organization=vendor, contact_row=contact_row)
            row_warnings.extend(ImportRowWarning(row_number=row_number, message=message) for message in result.warnings)
            by_pk = contact_products.setdefault(result.affiliation, {})
            by_pk.update((product.pk, product) for product in products)

        import_file_service.process_numbered_rows(rows=iter(rows), handler=_handle_row)

        if {"products", "contact_full_name"} <= columns:
            for affiliation, products in contact_products.items():
                contact_affiliation_service.set_products(affiliation=affiliation, products=products.values())

        if warnings is not None:
            warnings.extend(row_warnings)
        return len(created_ids), len(updated_ids)

    def _upsert_vendor(self, row: dict, touched: set) -> tuple[Vendor, bool]:
        """
        Вендор строки: по external_code, иначе по названию без учёта регистра и кавычек; True — создан.

        Вендор, уже обновлённый предыдущей строкой файла, повторно не перезаписывается.
        """
        name = normalize_quotes(import_file_service.to_text(row.get("name")))
        if not name:
            raise ValueError("поле name обязательно")
        external_code = import_file_service.to_text(row.get("external_code")) or None

        vendor = None
        if external_code:
            vendor = Vendor.objects.filter(external_code__iexact=external_code).first()
        if vendor is None:
            vendor = self._find_by_name(queryset=Vendor.objects.all(), name=name, label="вендоров")

        values = {"name": name}
        if "is_active" in row:
            values["is_active"] = import_file_service.to_bool(row["is_active"])
        if external_code:
            values["external_code"] = external_code

        if vendor is None:
            return Vendor.objects.create(**values), True
        if vendor.pk not in touched:
            for field, value in values.items():
                setattr(vendor, field, value)
            vendor.save(update_fields=[*values, "updated_at"])
        return vendor, False

    def _resolve_products(self, vendor: Vendor, raw_value) -> tuple[list[Product], list[str]]:
        """Продукты ячейки: найденные у вендора, «усыновлённые» без вендора или созданные; и предупреждения."""
        products: list[Product] = []
        warnings: list[str] = []
        for name in import_file_service.split_quoted_names(raw_value):
            product = self._find_by_name(queryset=vendor.products.all(), name=name, label="продуктов вендора")
            if product is None:
                product = self._find_by_name(
                    queryset=Product.objects.filter(vendor__isnull=True), name=name, label="продуктов без вендора"
                )
                if product is not None:
                    product.vendor = vendor
                    product.save(update_fields=["vendor", "updated_at"])
            if product is None:
                others = [
                    str(other.vendor)
                    for other in Product.objects.filter(vendor__isnull=False).select_related("vendor")
                    if quote_insensitive_key(other.name) == quote_insensitive_key(name)
                ]
                product = Product.objects.create(name=name, vendor=vendor)
                if others:
                    warnings.append(
                        f"продукт {name} создан у вендора {vendor}, продукт с таким названием уже есть у вендора "
                        f"{', '.join(others)}"
                    )
            products.append(product)
        return products, warnings

    def _find_by_name(self, queryset, name: str, label: str):
        """
        Запись с названием без учёта регистра, а если такой нет — без учёта вида кавычек; нет — None.

        Несколько записей, совпавших только без учёта кавычек, — `CatalogImportError`.
        """
        exact = queryset.filter(name__iexact=name).first()
        if exact is not None:
            return exact
        key = quote_insensitive_key(name)
        matches = [item for item in queryset if quote_insensitive_key(item.name) == key]
        if len(matches) > 1:
            raise CatalogImportError(f"среди {label} несколько совпадений с {name}: {', '.join(str(item) for item in matches)}")
        return matches[0] if matches else None


vendor_import_service = VendorImportService()
