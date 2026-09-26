"""Готовое для отображения представление отчёта.

Этот модуль является единственным местом, где принимаются решения о составе,
порядке и подписях графиков. Клиент получает уже агрегированные значения и не
должен повторять эти правила.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from django.utils import timezone

from sova.reports.services.dataset import ReportRow

from .summary import NO_ACTIVE_STAGE, NO_PROCESS, NO_RESPONSIBLE

MAX_CHART_ITEMS = 8

TEXT = {
    "ru": {
        "interactions": "Взаимодействия",
        "rows": "Строки",
        "programs": "Программы",
        "products": "Продукты",
        "by_responsible": "По ответственным",
        "by_university": "По вузам",
        "by_process_status": "По статусу процесса",
        "by_active_stage": "По актуальному этапу",
        "interactions_over_time": "Динамика взаимодействий",
        "value_interactions": "Взаимодействия",
        "empty": "Нет данных",
        "other": "Остальные",
        "period_day": "по дням",
        "period_week": "по неделям",
        "period_month": "по месяцам",
        "multiple_assignment": "Взаимодействие может учитываться в нескольких группах",
    },
    "en": {
        "interactions": "Interactions",
        "rows": "Rows",
        "programs": "Programs",
        "products": "Products",
        "by_responsible": "By manager",
        "by_university": "By university",
        "by_process_status": "By process status",
        "by_active_stage": "By current stage",
        "interactions_over_time": "Interactions over time",
        "value_interactions": "Interactions",
        "empty": "No data",
        "other": "Other",
        "period_day": "by day",
        "period_week": "by week",
        "period_month": "by month",
        "multiple_assignment": "An interaction may be counted in multiple groups",
    },
}

MONTHS = {
    "ru": ("янв.", "февр.", "марта", "апр.", "мая", "июн.", "июл.", "авг.", "сент.", "окт.", "нояб.", "дек."),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}


def _display_number(value: int, locale: str) -> str:
    return f"{value:,}".replace(",", "\u00a0" if locale == "ru" else ",")


def _item(key: str | None, label: str, value: int, locale: str) -> dict:
    return {
        "key": key,
        "label": label,
        "value": value,
        "display_value": _display_number(value, locale),
    }


def _distribution(groups: dict, labels: dict, locale: str) -> list[dict]:
    items = sorted(
        ((key, len(ids), labels.get(key, "")) for key, ids in groups.items()),
        key=lambda item: (-item[1], item[2]),
    )
    visible = [_item(None if key is None else str(key), label, value, locale) for key, value, label in items[:MAX_CHART_ITEMS]]
    rest = sum(value for _, value, _ in items[MAX_CHART_ITEMS:])
    if rest:
        visible.append(_item("other", TEXT[locale]["other"], rest, locale))
    return visible


def _month_start(value: dt.date) -> dt.date:
    return value.replace(day=1)


def _next_month(value: dt.date) -> dt.date:
    return value.replace(year=value.year + (value.month == 12), month=1 if value.month == 12 else value.month + 1)


def _bucket(value: dt.date, granularity: str) -> dt.date:
    if granularity == "day":
        return value
    if granularity == "week":
        return value - dt.timedelta(days=value.weekday())
    return _month_start(value)


def _next_bucket(value: dt.date, granularity: str) -> dt.date:
    if granularity == "day":
        return value + dt.timedelta(days=1)
    if granularity == "week":
        return value + dt.timedelta(days=7)
    return _next_month(value)


def _granularity(start: dt.date | None, end: dt.date | None) -> str:
    if not start or not end:
        return "month"
    days = (end - start).days + 1
    if days <= 31:
        return "day"
    if days <= 180:
        return "week"
    return "month"


def _period_label(value: dt.date, granularity: str, locale: str) -> str:
    if granularity == "day":
        return value.strftime("%d.%m.%Y" if locale == "ru" else "%d/%m/%Y")
    if granularity == "week":
        end = value + dt.timedelta(days=6)
        return f"{value:%d.%m}–{end:%d.%m}" if locale == "ru" else f"{value:%d %b}–{end:%d %b}"
    return f"{MONTHS[locale][value.month - 1]} {value.year}"


def _build_trend(
    buckets: dict[dt.date, set],
    rows_start: dt.date | None,
    rows_end: dt.date | None,
    locale: str,
) -> tuple[str, list[dict]]:
    granularity = _granularity(rows_start, rows_end)
    if not rows_start or not rows_end:
        return granularity, []
    current = _bucket(rows_start, granularity)
    last = _bucket(rows_end, granularity)
    points = []
    while current <= last:
        value = len(buckets.get(current, set()))
        points.append({
            "key": current.isoformat(),
            "label": _period_label(current, granularity, locale),
            "value": value,
            "display_value": _display_number(value, locale),
        })
        current = _next_bucket(current, granularity)
    return granularity, points


def build_report_presentation(
    rows: Iterable[ReportRow],
    *,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    locale: str = "ru",
) -> dict:
    """Агрегирует строки отчёта в готовые карточки и графики за один проход."""
    locale = locale if locale in TEXT else "ru"
    text = TEXT[locale]
    interactions: set = set()
    programs: set = set()
    products: set = set()
    by_responsible = defaultdict(set)
    responsible_names: dict = {}
    by_university = defaultdict(set)
    university_names: dict = {}
    by_process_status = defaultdict(set)
    process_labels: dict = {}
    by_stage = defaultdict(set)
    trend_dates: defaultdict[dt.date, set] = defaultdict(set)
    rows_count = 0
    observed_dates: list[dt.date] = []

    for row in rows:
        rows_count += 1
        interactions.add(row.interaction_id)
        if row.interaction_program_id:
            programs.add(row.interaction_program_id)
        if row.interaction_product_id:
            products.add(row.interaction_product_id)

        if row.responsible_ids:
            for responsible_id, name in zip(row.responsible_ids, row.responsible):
                by_responsible[responsible_id].add(row.interaction_id)
                responsible_names[responsible_id] = name
        else:
            by_responsible[None].add(row.interaction_id)
            responsible_names[None] = NO_RESPONSIBLE
        by_university[row.university_id].add(row.interaction_id)
        university_names[row.university_id] = row.university

        if row.process_statuses:
            for item in row.process_statuses:
                by_process_status[item["status"]].add(row.interaction_id)
                process_labels[item["status"]] = item["label"]
        else:
            by_process_status[None].add(row.interaction_id)
            process_labels[None] = NO_PROCESS

        if row.active_stages:
            for stage in row.active_stages:
                by_stage[stage.name].add(row.interaction_id)
        else:
            by_stage[None].add(row.interaction_id)

        row_date = timezone.localtime(row.created_at).date()
        observed_dates.append(row_date)
        trend_dates[row_date].add(row.interaction_id)

    start = date_from or (min(observed_dates) if observed_dates else None)
    end = date_to or (max(observed_dates) if observed_dates else None)
    selected_granularity = _granularity(start, end)
    trend = defaultdict(set)
    for row_date, interaction_ids in trend_dates.items():
        trend[_bucket(row_date, selected_granularity)].update(interaction_ids)
    granularity, points = _build_trend(trend, start, end, locale)

    def raw_distribution(groups, labels, key_name):
        return [
            {
                key_name: None if key is None else str(key),
                "label": label,
                "interactions": value,
            }
            for key, value, label in sorted(
                ((key, len(ids), labels.get(key, "")) for key, ids in groups.items()),
                key=lambda item: (-item[1], item[2]),
            )
        ]

    charts = [
        {
            "id": "interactions_over_time",
            "kind": "line",
            "title": text["interactions_over_time"],
            "description": text[f"period_{granularity}"],
            "value_label": text["value_interactions"],
            "empty_message": text["empty"],
            "tone": "primary",
            "points": points,
        },
    ]
    for chart_id, title_key, groups, labels, note in (
        ("by_responsible", "by_responsible", by_responsible, responsible_names, True),
        ("by_university", "by_university", by_university, university_names, False),
        ("by_process_status", "by_process_status", by_process_status, process_labels, True),
        ("by_active_stage", "by_active_stage", by_stage, {None: NO_ACTIVE_STAGE, **{key: key for key in by_stage if key is not None}}, True),
    ):
        chart = {
            "id": chart_id,
            "kind": "horizontal_bar",
            "title": text[title_key],
            "description": text["multiple_assignment"] if note else "",
            "value_label": text["value_interactions"],
            "empty_message": text["empty"],
            "tone": "primary",
            "items": _distribution(groups, labels, locale),
        }
        charts.append(chart)

    metrics = [
        ("interactions", len(interactions)),
        ("rows", rows_count),
        ("programs", len(programs)),
        ("products", len(products)),
    ]
    return {
        "interactions_count": len(interactions),
        "rows_count": rows_count,
        "programs_count": len(programs),
        "products_count": len(products),
        "by_responsible": raw_distribution(by_responsible, responsible_names, "id"),
        "by_university": raw_distribution(by_university, university_names, "id"),
        "by_process_status": raw_distribution(by_process_status, process_labels, "status"),
        "by_active_stage": raw_distribution(by_stage, {None: NO_ACTIVE_STAGE, **{key: key for key in by_stage if key is not None}}, "stage"),
        "metrics": [
            {"id": key, "label": text[key], "value": value, "display_value": _display_number(value, locale)}
            for key, value in metrics
        ],
        "charts": charts,
        "chart_meta": {"locale": locale, "granularity": granularity},
    }
