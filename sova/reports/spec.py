"""Нормализованный запрос на построение отчёта и белый список колонок."""

from __future__ import annotations

import datetime
import uuid
from dataclasses import asdict, dataclass

from sova.reports.enum import ReportFormat, ReportOrdering


@dataclass(frozen=True, slots=True)
class Column:
    """Отображаемая колонка отчёта: ключ в строке и заголовок в файле."""

    key: str
    title: str


# Порядок колонок в файлах фиксирован этим списком, а не порядком в запросе клиента
INTERACTION_COLUMNS: tuple[Column, ...] = (
    Column("organization", "Организация"),
    Column("direction", "Направление"),
    Column("program", "Программа"),
    Column("product", "Продукт"),
    Column("process_status", "Статус процесса"),
    Column("active_stages", "Актуальные этапы"),
    Column("responsible", "Ответственные"),
    Column("created_at", "Дата создания взаимодействия"),
    Column("updated_at", "Дата обновления взаимодействия"),
    Column("contract_numbers", "Договоры"),
    Column("contract_signed_at", "Договор подписан"),
    Column("license_status", "Лицензия"),
    Column("license_valid_until_year", "Лицензия действует до"),
)
INTERACTION_COLUMN_KEYS: tuple[str, ...] = tuple(column.key for column in INTERACTION_COLUMNS)
COLUMN_TITLES: dict[str, str] = {column.key: column.title for column in INTERACTION_COLUMNS}

# Идентификаторы и связи есть в каждой строке API и JSON-выгрузки независимо от выбора колонок
ID_FIELDS: tuple[str, ...] = (
    "interaction_id",
    "organization_id",
    "direction_id",
    "interaction_direction_id",
    "program_id",
    "interaction_program_id",
    "product_id",
    "interaction_product_id",
    "responsible_ids",
)


@dataclass(frozen=True)
class ReportSpec:
    """
    Параметры отчёта по взаимодействиям.

    Период — даты создания взаимодействия в часовом поясе проекта.
    Пустой список фильтра означает «без ограничения». Хранится в `ReportJob.spec`
    в виде `to_dict()`, поэтому фоновое задание строит ровно тот же отчёт.
    """

    date_from: datetime.date | None = None
    date_to: datetime.date | None = None
    organizations: tuple[uuid.UUID, ...] = ()
    directions: tuple[uuid.UUID, ...] = ()
    programs: tuple[uuid.UUID, ...] = ()
    products: tuple[uuid.UUID, ...] = ()
    responsibles: tuple[int, ...] = ()
    ordering: str = ReportOrdering.CREATED_AT_DESC
    columns: tuple[str, ...] = INTERACTION_COLUMN_KEYS
    format: str = ReportFormat.XLSX

    @property
    def selected_columns(self) -> tuple[Column, ...]:
        """Выбранные колонки в каноническом порядке."""
        selected = set(self.columns)
        return tuple(column for column in INTERACTION_COLUMNS if column.key in selected)

    def to_dict(self) -> dict:
        """JSON-представление для хранения в задании и метаданных ответа."""
        data = asdict(self)
        data["date_from"] = self.date_from.isoformat() if self.date_from else None
        data["date_to"] = self.date_to.isoformat() if self.date_to else None
        for name in ("organizations", "directions", "programs", "products"):
            data[name] = [str(value) for value in data[name]]
        data["responsibles"] = list(self.responsibles)
        data["columns"] = [column.key for column in self.selected_columns]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> ReportSpec:
        """Восстанавливает спецификацию из `to_dict()`."""

        def parse_date(value):
            return datetime.date.fromisoformat(value) if value else None

        return cls(
            date_from=parse_date(data.get("date_from")),
            date_to=parse_date(data.get("date_to")),
            organizations=tuple(uuid.UUID(str(v)) for v in data.get("organizations", ())),
            directions=tuple(uuid.UUID(str(v)) for v in data.get("directions", ())),
            programs=tuple(uuid.UUID(str(v)) for v in data.get("programs", ())),
            products=tuple(uuid.UUID(str(v)) for v in data.get("products", ())),
            responsibles=tuple(int(v) for v in data.get("responsibles", ())),
            ordering=data.get("ordering", ReportOrdering.CREATED_AT_DESC),
            columns=tuple(data.get("columns") or INTERACTION_COLUMN_KEYS),
            format=data.get("format", ReportFormat.XLSX),
        )
