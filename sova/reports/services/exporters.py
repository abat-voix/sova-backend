"""
Выгрузка отчёта в файлы. Все форматы получают одни и те же строки, порядок и колонки
из `ReportDataset` и одинаковый заголовок с метаданными.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Callable
from html import escape
from typing import BinaryIO

import xlwt
from django.conf import settings
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

from reports.pdf import html_to_pdf
from sova.reports.enum import ReportFormat
from sova.reports.services.dataset import STATE_NOTE, ReportDataset

REPORT_TITLE = "Отчёт по взаимодействиям с вузами"
CONTENT_TYPES = {
    ReportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ReportFormat.XLS: "application/vnd.ms-excel",
    ReportFormat.PDF: "application/pdf",
    ReportFormat.JSON: "application/json",
}
# Старый формат XLS: 65 536 строк на лист, из них одна — заголовок таблицы
XLS_MAX_ROWS = 65_536
XLS_MAX_CELL_LENGTH = 32_767


class ReportTooLargeError(ValueError):
    """Выборка превышает ограничение формата."""


def header_lines(dataset: ReportDataset) -> list[str]:
    """Строки заголовка файла: период, фильтры и семантика состояния."""
    spec = dataset.spec
    period_from = spec.date_from.strftime("%d.%m.%Y") if spec.date_from else "—"
    period_to = spec.date_to.strftime("%d.%m.%Y") if spec.date_to else "—"
    lines = [
        REPORT_TITLE,
        f"Сформирован: {timezone.localtime(dataset.generated_at).strftime('%d.%m.%Y %H:%M')}",
        f"Период создания взаимодействий: {period_from} – {period_to}",
    ]
    filters = [
        ("Вузы", spec.universities),
        ("Направления", spec.directions),
        ("Программы", spec.programs),
        ("Продукты", spec.products),
        ("Ответственные", spec.responsibles),
    ]
    applied = [f"{name}: {len(values)}" for name, values in filters if values]
    lines.append("Фильтры: " + (", ".join(applied) if applied else "не заданы"))
    lines.append(STATE_NOTE)
    return lines


def _cell(value):
    if isinstance(value, datetime.date):
        return value.isoformat()
    return value


def export_xlsx(dataset: ReportDataset, out: BinaryIO) -> None:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Отчёт")
    columns = dataset.columns
    for line in header_lines(dataset):
        sheet.append([line])
    sheet.append([])
    header = []
    for column in columns:
        cell = WriteOnlyCell(sheet, value=column.title)
        cell.font = Font(bold=True)
        header.append(cell)
    sheet.append(header)
    for row in dataset.iter_rows():
        sheet.append([_cell(row.display_value(column.key)) for column in columns])
    workbook.save(out)


def export_xls(dataset: ReportDataset, out: BinaryIO) -> None:
    workbook = xlwt.Workbook(encoding="utf-8")
    bold = xlwt.easyxf("font: bold on")
    columns = dataset.columns
    lines = header_lines(dataset)
    max_sheets = settings.REPORTS_XLS_MAX_SHEETS

    def new_sheet(number: int):
        if number > max_sheets:
            raise ReportTooLargeError("Выборка слишком велика для формата XLS; выберите XLSX.")
        sheet = workbook.add_sheet(f"Отчёт {number}" if number > 1 else "Отчёт")
        for index, line in enumerate(lines):
            sheet.write(index, 0, line)
        header_row = len(lines) + 1
        for index, column in enumerate(columns):
            sheet.write(header_row, index, column.title, bold)
        return sheet, header_row + 1

    sheet_number = 1
    sheet, row_index = new_sheet(sheet_number)
    for row in dataset.iter_rows():
        if row_index >= XLS_MAX_ROWS:
            sheet_number += 1
            sheet, row_index = new_sheet(sheet_number)
        for index, column in enumerate(columns):
            value = _cell(row.display_value(column.key))
            if isinstance(value, str):
                value = value[:XLS_MAX_CELL_LENGTH]
            sheet.write(row_index, index, value)
        row_index += 1
    workbook.save(out)


def export_json(dataset: ReportDataset, out: BinaryIO) -> None:
    """JSON с идентификаторами и связями для интеграции; строки пишутся потоково."""
    columns = dataset.columns
    out.write(b'{"meta": ')
    out.write(json.dumps(dataset.metadata(), ensure_ascii=False).encode())
    out.write(b', "rows": [')
    for index, row in enumerate(dataset.iter_rows()):
        if index:
            out.write(b", ")
        out.write(json.dumps(row.to_dict(columns), ensure_ascii=False).encode())
    out.write(b"]}")


PDF_STYLE = """
@page { size: A4 landscape; margin: 12mm; }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 8pt; }
h1 { font-size: 13pt; margin: 0 0 4mm; }
p.meta { margin: 0 0 1mm; color: #333; }
table { border-collapse: collapse; width: 100%; margin-top: 4mm; }
th, td { border: 1px solid #999; padding: 1mm 1.5mm; text-align: left; vertical-align: top; }
th { background: #eee; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
"""


def export_pdf(dataset: ReportDataset, out: BinaryIO) -> None:
    columns = dataset.columns
    max_rows = settings.REPORTS_PDF_MAX_ROWS
    lines = header_lines(dataset)
    parts = [
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">',
        f"<title>{escape(REPORT_TITLE)}</title><style>{PDF_STYLE}</style></head><body>",
        f"<h1>{escape(lines[0])}</h1>",
        *(f'<p class="meta">{escape(line)}</p>' for line in lines[1:]),
        "<table><thead><tr>",
        *(f"<th>{escape(column.title)}</th>" for column in columns),
        "</tr></thead><tbody>",
    ]
    for index, row in enumerate(dataset.iter_rows()):
        if index >= max_rows:
            raise ReportTooLargeError(
                f"Для PDF допускается не более {max_rows} строк; сузьте фильтры или выберите XLSX."
            )
        cells = "".join(f"<td>{escape(str(_cell(row.display_value(c.key))))}</td>" for c in columns)
        parts.append(f"<tr>{cells}</tr>")
    parts.append("</tbody></table></body></html>")
    out.write(html_to_pdf("".join(parts), form_fields={"landscape": True}))


EXPORTERS: dict[str, Callable[[ReportDataset, BinaryIO], None]] = {
    ReportFormat.XLSX: export_xlsx,
    ReportFormat.XLS: export_xls,
    ReportFormat.PDF: export_pdf,
    ReportFormat.JSON: export_json,
}


def export(dataset: ReportDataset, report_format: str, out: BinaryIO) -> None:
    """Пишет отчёт в `out` в заданном формате."""
    EXPORTERS[report_format](dataset, out)
