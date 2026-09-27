import codecs
import re
from collections.abc import Callable, Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from io import BytesIO, StringIO
from pathlib import Path
from typing import TypeVar
from zipfile import BadZipFile

import xlrd
from django.core.files import File
from django.db import transaction
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from sova.catalog.enum import ContactChannel
from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.models import CatalogImportMapping
from sova.catalog.schemas import ImportRowError
from sova.core.text import normalize_text, quote_insensitive_key, split_quoted_list, strip_outer_quotes, text_key

Rows = Iterator[tuple[int, dict]]
# Путь на диске (CLI) или загруженный файл (API) — у обоих есть name с расширением.
ImportSource = Path | File
RowResult = TypeVar("RowResult")

_TRUE_VALUES = {"1", "true", "да", "yes"}
# Способы связи в файлах импорта (ключ — `quote_insensitive_key`) → ContactChannel.
_CONTACT_CHANNEL_SYNONYMS = {
    **dict.fromkeys(("почта", "email", "e-mail", "эл. почта", "электронная почта"), ContactChannel.EMAIL.value),
    **dict.fromkeys(
        ("чат в тг", "тг", "telegram", "телеграм", "телеграмм", "чат в telegram"), ContactChannel.TELEGRAM.value
    ),
    **dict.fromkeys(("телефон", "звонок", "phone"), ContactChannel.PHONE.value),
    **dict.fromkeys(("другое", "other"), ContactChannel.OTHER.value),
}
_FALSE_VALUES = {"0", "false", "нет", "no"}
_DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d")

# Сигнатуры по первым байтам: xlsx — zip-архив, xls — OLE-контейнер (Excel 97+) или «голый» BIFF2–4.
_XLSX_SIGNATURE = b"PK\x03\x04"
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_BIFF_SIGNATURES = (b"\x09\x00", b"\x09\x02", b"\x09\x04")
_UTF8_BOM = b"\xef\xbb\xbf"

# Старые xls без записи CODEPAGE xlrd читает как latin-1 — для русскоязычных файлов это cp1251.
_FALLBACK_ENCODING = "cp1251"


class ImportFileService:
    """
    Файл импорта каталога: чтение строк, заголовков и значений ячеек, построчная обработка.

    Читает первый лист xlsx (openpyxl) или старого xls (xlrd) — формат по расширению имени файла.
    Отдаёт строки в виде {канонический ключ: значение} — либо через настраиваемый
    `CatalogImportMapping`, либо как есть, если заголовки файла уже совпадают с ключами (CLI).
    Обработчики каталогов работают только с каноническими ключами и о файле ничего не знают.
    """

    def read_mapped_rows(self, catalog_type: str, source: ImportSource, required: set[str]) -> Rows:
        """Читает файл и переводит заголовки в канонические ключи через CatalogImportMapping."""
        headers, raw_rows = self._read_raw_rows(source=source)
        header_to_key = self._resolve_header_map(catalog_type=catalog_type, headers=headers)
        self._require_fields(
            present=set(header_to_key.values()), required=required, context=self._file_name(source=source)
        )
        return self._translate_rows(raw_rows=raw_rows, header_to_key=header_to_key)

    def read_canonical_rows(self, source: ImportSource, required: set[str]) -> Rows:
        """Читает файл, заголовки которого уже являются каноническими ключами (без маппинга)."""
        headers, raw_rows = self._read_raw_rows(source=source)
        self._require_fields(present=set(headers), required=required, context=self._file_name(source=source))
        return raw_rows

    def process_rows(self, rows: Rows, handler: Callable[[dict], RowResult]) -> list[RowResult]:
        """
        Применяет handler к каждой строке и собирает ошибки всех строк, а не только первой.

        Каждая строка — в своей точке сохранения, поэтому ошибка строки не ломает транзакцию и
        обработка продолжается. Если ошибки есть — `CatalogImportRowsError` со всеми ошибками;
        вызывать внутри `transaction.atomic`, чтобы исключение откатило весь импорт.
        """
        return self.process_numbered_rows(rows=rows, handler=lambda _row_number, row: handler(row))

    def process_numbered_rows(self, rows: Rows, handler: Callable[[int, dict], RowResult]) -> list[RowResult]:
        """Как `process_rows`, но handler получает и номер строки — для предупреждений по строке."""
        results: list[RowResult] = []
        errors: list[ImportRowError] = []

        for row_number, row in rows:
            try:
                with transaction.atomic():
                    results.append(handler(row_number, row))
            except KeyError as error:
                errors.append(ImportRowError(row_number=row_number, message=f"отсутствует поле {error}"))
            except (CatalogImportError, InvalidOperation, TypeError, ValueError) as error:
                errors.append(ImportRowError(row_number=row_number, message=str(error)))

        if errors:
            raise CatalogImportRowsError(errors=errors)
        return results

    def to_text(self, value) -> str:
        """Значение ячейки как нормализованная строка (normalize_text); пустая ячейка — пустая строка."""
        return "" if value is None else normalize_text(str(value))

    def to_bool(self, value) -> bool:
        """Флаг is_active: пустая ячейка — True, иначе да/нет/1/0/true/false."""
        if value is None or value == "":
            return True
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in _TRUE_VALUES:
            return True
        if text in _FALSE_VALUES:
            return False
        raise ValueError(f"ожидалось булево значение is_active, получено {value}")

    def is_true(self, value) -> bool:
        """Строгая проверка «да»: пустая или непонятная ячейка — False."""
        return self.to_text(value).lower() in _TRUE_VALUES

    def to_decimal(self, value) -> Decimal | None:
        """Число с плавающей точкой; пустая ячейка — None."""
        if value in (None, ""):
            return None
        return self._parse_number(value=value)

    def to_positive_int(self, value) -> int:
        """Целое неотрицательное число; пустая ячейка — 0."""
        if value in (None, ""):
            return 0
        number = self._parse_number(value=value)
        if number < 0 or number != number.to_integral_value():
            raise ValueError(f"ожидалось целое неотрицательное число, получено {value}")
        return int(number)

    def to_date(self, value) -> date | None:
        """Дата из ячейки-даты или текста ДД.ММ.ГГГГ / ГГГГ-ММ-ДД (HTML под видом xls); иначе None."""
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            for date_format in _DATE_FORMATS:
                try:
                    return datetime.strptime(value.strip(), date_format).date()
                except ValueError:
                    continue
        return None

    def to_year(self, value) -> int | None:
        """Год (в xlsx может прийти числом с дробной частью); пустая ячейка — None."""
        text = self.to_text(value)
        if not text:
            return None
        year = self._parse_number(value=text)
        if year != year.to_integral_value():
            raise ValueError(f"ожидался год целым числом, получено {value}")
        return int(year)

    def split_list(self, value) -> list[str]:
        """Список значений, перечисленных в ячейке через «;»."""
        return [part.strip() for part in self.to_text(value).split(";") if part.strip()]

    def split_quoted_names(self, value) -> list[str]:
        """
        Названия, перечисленные через «,» или «;» вне кавычек, без внешней пары кавычек у каждого.

        «RT.DataLake», «RT.Warehouse» → [RT.DataLake, RT.Warehouse]; «Система «Яга»» → [Система «Яга»].
        Повторы (без учёта регистра и вида кавычек) схлопываются; непарные кавычки — ValueError.
        """
        names: dict[str, str] = {}
        for item in split_quoted_list(self.to_text(value)):
            name = strip_outer_quotes(item)
            if name:
                names.setdefault(quote_insensitive_key(name), name)
        return list(names.values())

    def to_contact_channels(self, value) -> list[str]:
        """
        Способы связи из ячейки через «,» или «;»: «Почта, Чат в ТГ» → [email, telegram].

        Значение сравнивается со словарём синонимов без учёта регистра; неизвестное — ValueError.
        """
        channels: list[str] = []
        for item in split_quoted_list(self.to_text(value)):
            channel = _CONTACT_CHANNEL_SYNONYMS.get(quote_insensitive_key(item))
            if channel is None:
                allowed = ", ".join(sorted({synonym for synonym in _CONTACT_CHANNEL_SYNONYMS}))
                raise ValueError(f"неизвестный способ связи {item}; допустимые: {allowed}")
            if channel not in channels:
                channels.append(channel)
        return channels

    def _parse_number(self, value) -> Decimal:
        """Конечное число из ячейки; текст вместо числа — ValueError с понятным сообщением."""
        try:
            number = Decimal(str(value).strip())
        except InvalidOperation:
            raise ValueError(f"ожидалось число, получено {value}") from None
        if not number.is_finite():
            raise ValueError(f"ожидалось число, получено {value}")
        return number

    def _read_raw_rows(self, source: ImportSource) -> tuple[list[str], Rows]:
        """
        Читает первый лист: нормализованные заголовки + построчные словари {заголовок: значение}.

        Формат определяется по содержимому, а не по расширению: 1С и веб-системы сохраняют HTML-таблицу
        под именем .xls, а пользователи переименовывают xls в xlsx. Текст ячеек нормализуется (normalize_text).
        """
        name = self._file_name(source=source)
        if Path(name).suffix.lower() not in (".xlsx", ".xls"):
            raise CatalogImportError(f"Неподдерживаемый формат файла {name}: ожидается .xlsx или .xls.")

        content = self._read_content(source=source)
        open_rows = {
            "xlsx": self._open_xlsx,
            "xls": self._open_xls,
            "html": self._open_html,
        }[self._detect_format(content=content, name=name)]
        rows, close = open_rows(content=content, name=name)

        try:
            raw_headers = next(rows)
        except StopIteration as error:
            close()
            raise CatalogImportError(f"Файл {name} пуст.") from error

        headers = [normalize_text(str(value)) if value is not None else "" for value in raw_headers]

        def _iter_rows() -> Rows:
            for row_number, values in enumerate(rows, start=2):
                values = [normalize_text(value) if isinstance(value, str) else value for value in values]
                if not any(value not in (None, "") for value in values):
                    continue
                yield row_number, dict(zip(headers, values, strict=False))
            close()

        return headers, _iter_rows()

    def _read_content(self, source: ImportSource) -> bytes:
        """Содержимое файла целиком — нужно для определения формата по первым байтам."""
        if isinstance(source, Path):
            return source.read_bytes()
        source.seek(0)
        return source.read()

    def _detect_format(self, content: bytes, name: str) -> str:
        """xlsx, xls или html — по сигнатуре содержимого; текст и XML-таблицы Excel 2003 не поддерживаются."""
        if content.startswith(_XLSX_SIGNATURE):
            return "xlsx"
        if content.startswith(_OLE_SIGNATURE) or content[:2] in _BIFF_SIGNATURES:
            return "xls"

        head = content[:2048].removeprefix(_UTF8_BOM).lstrip().lower()
        if head.startswith(b"<?xml") and b"urn:schemas-microsoft-com:office:spreadsheet" in content[:4096]:
            raise CatalogImportError(
                f"Файл {name} сохранён как «XML-таблица Excel 2003» — откройте его в Excel и сохраните как .xlsx."
            )
        if head.startswith(b"<") and (b"<html" in head or b"<table" in head or head.startswith(b"<!doctype html")):
            return "html"
        raise CatalogImportError(
            f"Не удалось распознать файл {name} как таблицу Excel: если это выгрузка в текстовом виде, "
            "откройте её в Excel и сохраните как .xlsx."
        )

    def _open_xlsx(self, content: bytes, name: str) -> tuple[Iterator[tuple], Callable[[], None]]:
        """Значения строк первого листа xlsx и функция закрытия книги (read_only читает лениво)."""
        try:
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        except (BadZipFile, InvalidFileException, KeyError) as error:
            raise CatalogImportError(f"Не удалось прочитать файл {name}: файл повреждён или это не xlsx.") from error
        return workbook.active.iter_rows(values_only=True), workbook.close

    def _open_xls(self, content: bytes, name: str) -> tuple[Iterator[tuple], Callable[[], None]]:
        """
        Значения строк первого листа xls; даты и целые числа приводятся к тому же виду, что у xlsx.

        Excel 97+ хранит текст в Юникоде. Старые файлы — в кодовой странице из записи CODEPAGE, а без неё
        xlrd читает латиницей: такой файл перечитывается в cp1251. Если CODEPAGE есть, ей доверяем.
        """
        book = self._open_xls_book(content=content, name=name, encoding_override=None)
        if book.biff_version < 80 and book.codepage is None:
            book.release_resources()
            book = self._open_xls_book(content=content, name=name, encoding_override=_FALLBACK_ENCODING)

        sheet = book.sheet_by_index(0)
        rows = (
            tuple(self._xls_value(cell=cell, datemode=book.datemode) for cell in sheet.row(index))
            for index in range(sheet.nrows)
        )
        return rows, book.release_resources

    def _open_xls_book(self, content: bytes, name: str, encoding_override: str | None) -> xlrd.Book:
        """Открывает xls; служебные сообщения xlrd (по умолчанию — в stdout) отбрасываются."""
        try:
            return xlrd.open_workbook(
                file_contents=content,
                encoding_override=encoding_override,
                logfile=StringIO(),
            )
        except (xlrd.XLRDError, xlrd.compdoc.CompDocError) as error:
            raise CatalogImportError(f"Не удалось прочитать файл {name}: файл повреждён или это не xls.") from error

    def _open_html(self, content: bytes, name: str) -> tuple[Iterator[tuple], Callable[[], None]]:
        """Строки первой таблицы HTML-файла, сохранённого под расширением .xls; все значения — текст."""
        parser = _HtmlTableParser()
        parser.feed(self._decode_html(content=content))
        parser.close()
        return iter(parser.rows), lambda: None

    def _decode_html(self, content: bytes) -> str:
        """
        Текст HTML: кодировка из BOM или meta charset, иначе UTF-8, а если он не подходит — cp1251.

        Выгрузки 1С и старых веб-систем часто в windows-1251 и без объявленной кодировки.
        """
        if content.startswith(_UTF8_BOM):
            return content.decode("utf-8-sig", errors="replace")

        declared = re.search(rb"charset\s*=\s*[\"']?([\w-]+)", content[:4096], flags=re.IGNORECASE)
        if declared:
            try:
                return content.decode(codecs.lookup(declared.group(1).decode("ascii")).name, errors="replace")
            except LookupError:
                pass

        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode(_FALLBACK_ENCODING, errors="replace")

    def _xls_value(self, cell: xlrd.sheet.Cell, datemode: int):
        """
        Значение ячейки xls в том же виде, что отдаёт openpyxl для xlsx.

        В xls даты хранятся числом (днями от эпохи книги), а все числа — float: без приведения
        код «1001» прочитался бы как «1001.0», а дата подписания лицензии — как число.
        """
        if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
            return None
        if cell.ctype == xlrd.XL_CELL_DATE:
            return xlrd.xldate.xldate_as_datetime(cell.value, datemode)
        if cell.ctype == xlrd.XL_CELL_BOOLEAN:
            return bool(cell.value)
        if cell.ctype == xlrd.XL_CELL_NUMBER and float(cell.value).is_integer():
            return int(cell.value)
        return cell.value

    def _file_name(self, source: ImportSource) -> str:
        """Имя файла без пути — для выбора формата и текста ошибок."""
        return Path(source.name).name

    def _resolve_header_map(self, catalog_type: str, headers: list[str]) -> dict[str, str]:
        """Строит {заголовок файла: канонический ключ} для замапленных колонок этого catalog_type."""
        configured = dict(
            CatalogImportMapping.objects.filter(catalog_type=catalog_type).values_list(
                "source_column", "target_field"
            )
        )
        if not configured:
            raise CatalogImportError(f"Для типа '{catalog_type}' не настроен маппинг ни одной колонки.")
        by_key = {text_key(source_column): target_field for source_column, target_field in configured.items()}
        header_keys = {header: text_key(header) for header in headers}
        return {header: by_key[key] for header, key in header_keys.items() if key in by_key}

    def _translate_rows(self, raw_rows: Rows, header_to_key: dict[str, str]) -> Rows:
        """Переводит сырые строки (заголовок → значение) в канонические ключи; лишние колонки отбрасывает."""
        for row_number, row in raw_rows:
            yield row_number, {
                header_to_key[header]: value for header, value in row.items() if header in header_to_key
            }

    def _require_fields(self, present: set[str], required: set[str], context: str) -> None:
        """Проверяет, что все обязательные канонические ключи есть в файле."""
        missing = sorted(required - present)
        if missing:
            raise CatalogImportError(f"{context}: отсутствуют поля: {', '.join(missing)}")


import_file_service = ImportFileService()


class _HtmlTableParser(HTMLParser):
    """
    Собирает строки первой таблицы HTML: ячейки td/th как текст, <br> — перенос строки внутри ячейки.

    Незакрытые <td>/<tr> (так пишут некоторые выгрузки) закрываются следующим открывающим тегом.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple] = []
        self._table_depth = 0
        self._done = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self._done:
            return
        if tag == "table":
            self._table_depth += 1
        elif self._table_depth != 1:
            # Вложенные таблицы — часть ячейки внешней, отдельными строками их не считаем.
            return
        elif tag == "tr":
            self._finish_row()
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._finish_cell()
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        if tag == "table":
            if self._table_depth == 1:
                self._finish_row()
            self._table_depth -= 1
            self._done = self._table_depth == 0
        elif self._table_depth != 1:
            return
        elif tag in ("td", "th"):
            self._finish_cell()
        elif tag == "tr":
            self._finish_row()

    def handle_data(self, data: str) -> None:
        if self._cell is not None and self._table_depth == 1:
            self._cell.append(data)

    def _finish_cell(self) -> None:
        if self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell))
        self._cell = None

    def _finish_row(self) -> None:
        self._finish_cell()
        if self._row is not None:
            self.rows.append(tuple(self._row))
        self._row = None
