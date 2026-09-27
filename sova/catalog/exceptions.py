from sova.catalog.schemas import ImportRowError


class CatalogImportError(Exception):
    """Строка или файл импорта каталога не могут быть обработаны."""


class CatalogImportRowsError(CatalogImportError):
    """В строках файла импорта есть ошибки — импорт откачен целиком, `errors` содержит все ошибки."""

    def __init__(self, errors: list[ImportRowError]) -> None:
        self.errors = errors
        lines = "\n".join(str(error) for error in errors)
        super().__init__(f"Импорт отменён, ошибок в строках: {len(errors)}\n{lines}")


class CatalogImportMappingError(Exception):
    """Маппинг типа каталога не прошёл проверку — `errors` содержит ошибки по каноническим ключам."""

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__("; ".join(f"{key}: {message}" for key, message in errors.items()))
