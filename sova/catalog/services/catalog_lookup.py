from sova.catalog.exceptions import CatalogImportError
from sova.catalog.models import Direction, Product, Program, Organization, Vendor
from sova.catalog.services.import_file import import_file_service


class CatalogLookupService:
    """
    Поиск записей справочников по значению ячейки файла импорта.

    Организация, вендор и направление ищутся сначала по external_code, затем по name; программа и продукт —
    по name. Сравнение без учёта регистра — как у ограничений уникальности моделей. Не найденное значение — `CatalogImportError` (номер строки добавляет
    `ImportFileService.process_rows`).
    """

    def find_organization(self, raw_value) -> Organization:
        """Обязательная организация."""
        value = import_file_service.to_text(raw_value)
        if not value:
            raise CatalogImportError("поле organization обязательно")
        organization = (
            Organization.objects.filter(external_code__iexact=value).first()
            or Organization.objects.filter(name__iexact=value).first()
        )
        if organization is None:
            raise CatalogImportError(f"организация не найдена: {value}")
        return organization

    def find_vendor(self, raw_value) -> Vendor | None:
        """Необязательный вендор: пустая ячейка — None."""
        value = import_file_service.to_text(raw_value)
        if not value:
            return None
        vendor = (
            Vendor.objects.filter(external_code__iexact=value).first()
            or Vendor.objects.filter(name__iexact=value).first()
        )
        if vendor is None:
            raise CatalogImportError(f"вендор не найден: {value}")
        return vendor

    def find_direction(self, raw_value) -> Direction:
        """Обязательное направление."""
        value = import_file_service.to_text(raw_value)
        if not value:
            raise CatalogImportError("поле direction обязательно")
        direction = (
            Direction.objects.filter(external_code__iexact=value).first()
            or Direction.objects.filter(name__iexact=value).first()
        )
        if direction is None:
            raise CatalogImportError(f"направление не найдено: {value}")
        return direction

    def find_program(self, name: str) -> Program:
        """Программа по точному имени."""
        program = Program.objects.filter(name__iexact=name).first()
        if program is None:
            raise CatalogImportError(f"программа не найдена: {name}")
        return program

    def find_programs(self, raw_value) -> list[Program]:
        """Программы, перечисленные в ячейке через «;»; пустая ячейка — пустой список."""
        return [self.find_program(name=name) for name in import_file_service.split_list(raw_value)]

    def find_product(self, raw_value, vendor: Vendor | None) -> Product:
        """Продукт по имени — в пределах вендора, если он указан."""
        value = import_file_service.to_text(raw_value)
        query = Product.objects.filter(name__iexact=value)
        if vendor is not None:
            query = query.filter(vendor=vendor)
        product = query.first()
        if product is None:
            raise CatalogImportError(f"продукт не найден: {value}")
        return product


catalog_lookup_service = CatalogLookupService()
