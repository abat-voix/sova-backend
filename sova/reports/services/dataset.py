"""
Единый набор строк отчёта по взаимодействиям.

Одна и та же проекция используется предпросмотром, статистикой и всеми форматами выгрузки,
поэтому их строки, порядок и фильтры совпадают при одинаковом `ReportSpec`.

Семантика:
- период — включительные даты `Interaction.created_at` в часовом поясе проекта;
- статус, ответственный и состав — состояние на момент построения (`generated_at`);
- строка — продукт взаимодействия с его программой и направлением; затем программы без
  продуктов, затем направления без программ; пустое взаимодействие — одна строка;
- актуальный этап — `StageInstance` со статусом `in_progress` на уровне взаимодействия
  или контекста строки (направление, программа, продукт).
"""

from __future__ import annotations

import datetime
import uuid
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field

from django.db.models import Exists, OuterRef, QuerySet, Subquery
from django.utils import timezone

from sova.interactions.models import (
    Contract,
    Interaction,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    License,
    Responsible,
)
from sova.interactions.services import visible_interactions
from sova.processes.enum import StageInstanceContextType, StageInstanceStatus
from sova.processes.models import StageInstance, WorkflowInstance
from sova.reports.enum import ReportOrdering
from sova.reports.spec import INTERACTION_COLUMNS, ReportSpec

BATCH_SIZE = 500
ACTIVE_STAGE_STATUS = StageInstanceStatus.IN_PROGRESS
LIST_SEPARATOR = "; "

PERIOD_BASIS = "interaction_created_at"
STATE_NOTE = (
    "Период — даты создания взаимодействия. Статус, этапы, ответственный "
    "и состав отражают состояние на момент построения отчёта. Актуальным считается этап "
    "со статусом «В работе»."
)


@dataclass(frozen=True, slots=True)
class Stage:
    """Актуальный этап строки."""

    id: uuid.UUID
    name: str
    context_type: str


@dataclass(slots=True)
class ReportRow:
    """Строка отчёта: идентификаторы, связи и отображаемые значения."""

    interaction_id: uuid.UUID
    university_id: uuid.UUID | None
    university: str
    created_at: datetime.datetime
    updated_at: datetime.datetime
    responsible_id: int | None = None
    responsible: str = ""
    direction_id: uuid.UUID | None = None
    interaction_direction_id: uuid.UUID | None = None
    direction: str = ""
    program_id: uuid.UUID | None = None
    interaction_program_id: uuid.UUID | None = None
    program: str = ""
    product_id: uuid.UUID | None = None
    interaction_product_id: uuid.UUID | None = None
    product: str = ""
    process_statuses: list[dict] = field(default_factory=list)
    active_stages: list[Stage] = field(default_factory=list)
    contract_numbers: list[str] = field(default_factory=list)
    contract_signed_at: list[datetime.date] = field(default_factory=list)
    license_status: str = ""
    license_valid_until_year: int | None = None

    def display_value(self, key: str):
        """Значение колонки для файловых форматов: списки склеиваются разделителем."""
        if key == "process_status":
            return LIST_SEPARATOR.join(item["label"] for item in self.process_statuses)
        if key == "active_stages":
            return LIST_SEPARATOR.join(stage.name for stage in self.active_stages)
        if key == "contract_numbers":
            return LIST_SEPARATOR.join(self.contract_numbers)
        if key == "contract_signed_at":
            return LIST_SEPARATOR.join(value.strftime("%d.%m.%Y") for value in self.contract_signed_at)
        if key in ("created_at", "updated_at"):
            return timezone.localtime(getattr(self, key)).strftime("%d.%m.%Y %H:%M")
        value = getattr(self, key)
        return "" if value is None else value

    def to_dict(self, columns) -> dict:
        """JSON-представление: все идентификаторы плюс выбранные колонки."""
        data = {
            "interaction_id": str(self.interaction_id),
            "university_id": _str_or_none(self.university_id),
            "direction_id": _str_or_none(self.direction_id),
            "interaction_direction_id": _str_or_none(self.interaction_direction_id),
            "program_id": _str_or_none(self.program_id),
            "interaction_program_id": _str_or_none(self.interaction_program_id),
            "product_id": _str_or_none(self.product_id),
            "interaction_product_id": _str_or_none(self.interaction_product_id),
            "responsible_id": self.responsible_id,
        }
        for column in columns:
            key = column.key
            if key == "process_status":
                data[key] = self.process_statuses
            elif key == "active_stages":
                data[key] = [
                    {"id": str(stage.id), "name": stage.name, "context_type": stage.context_type}
                    for stage in self.active_stages
                ]
            elif key == "contract_signed_at":
                data[key] = [value.isoformat() for value in self.contract_signed_at]
            elif key in ("created_at", "updated_at"):
                data[key] = timezone.localtime(getattr(self, key)).isoformat()
            else:
                data[key] = getattr(self, key)
        return data


def _str_or_none(value) -> str | None:
    return None if value is None else str(value)


@dataclass
class ReportDataset:
    """Выборка отчёта: ленивая итерация строк и метаданные построения."""

    user: object
    spec: ReportSpec
    generated_at: datetime.datetime = field(default_factory=timezone.now)

    @property
    def columns(self):
        return self.spec.selected_columns

    def interactions(self) -> QuerySet[Interaction]:
        """Базовая выборка: только видимые пользователю взаимодействия с вузами."""
        return filter_interactions(visible_interactions(self.user), self.spec)

    def iter_rows(self) -> Iterator[ReportRow]:
        """Строки отчёта в итоговом порядке, пачками по `BATCH_SIZE` взаимодействий."""
        ids = list(self.interactions().values_list("pk", flat=True))
        for start in range(0, len(ids), BATCH_SIZE):
            yield from _build_rows(ids[start:start + BATCH_SIZE], self.spec)

    def metadata(self) -> dict:
        """Метаданные, одинаковые для ответов API и заголовков файлов."""
        return {
            "report_type": "interactions",
            "generated_at": timezone.localtime(self.generated_at).isoformat(),
            "period_basis": PERIOD_BASIS,
            "active_stage_status": ACTIVE_STAGE_STATUS.value,
            "state_note": STATE_NOTE,
            "filters": self.spec.to_dict(),
            "columns": [{"key": c.key, "title": c.title} for c in self.columns],
            "available_columns": [{"key": c.key, "title": c.title} for c in INTERACTION_COLUMNS],
        }


def filter_interactions(queryset: QuerySet[Interaction], spec: ReportSpec) -> QuerySet[Interaction]:
    """
    Фильтры на уровне взаимодействия через `Exists`, без соединения состава в один запрос.

    Фильтры по направлению/программе/продукту здесь только отсекают взаимодействия;
    строки внутри взаимодействия ограничивает `_row_matches`.
    """
    queryset = queryset.filter(university__isnull=False)
    if spec.date_from:
        queryset = queryset.filter(created_at__date__gte=spec.date_from)
    if spec.date_to:
        queryset = queryset.filter(created_at__date__lte=spec.date_to)
    if spec.universities:
        queryset = queryset.filter(university_id__in=spec.universities)
    if spec.responsibles:
        queryset = queryset.filter(
            Exists(
                Responsible.objects.filter(
                    interaction=OuterRef("pk"),
                    unassigned_at__isnull=True,
                    manager_id__in=spec.responsibles,
                )
            )
        )
    if spec.products:
        products = InteractionProduct.objects.filter(
            interaction=OuterRef("pk"), is_active=True, product_id__in=spec.products
        )
        if spec.programs:
            products = products.filter(interaction_program__program_id__in=spec.programs)
        if spec.directions:
            products = products.filter(interaction_program__program__direction_id__in=spec.directions)
        queryset = queryset.filter(Exists(products))
    elif spec.programs:
        programs = InteractionProgram.objects.filter(
            interaction=OuterRef("pk"), is_active=True, program_id__in=spec.programs
        )
        if spec.directions:
            programs = programs.filter(program__direction_id__in=spec.directions)
        queryset = queryset.filter(Exists(programs))
    elif spec.directions:
        queryset = queryset.filter(
            Exists(
                InteractionDirection.objects.filter(
                    interaction=OuterRef("pk"), is_active=True, direction_id__in=spec.directions
                )
            )
            | Exists(
                InteractionProgram.objects.filter(
                    interaction=OuterRef("pk"), is_active=True, program__direction_id__in=spec.directions
                )
            )
        )
    return queryset.order_by(*_ordering(spec.ordering))


def _ordering(ordering: str) -> tuple:
    if ordering == ReportOrdering.CREATED_AT:
        return ("created_at", "pk")
    if ordering == ReportOrdering.UNIVERSITY:
        return ("university__name", "created_at", "pk")
    if ordering == ReportOrdering.RESPONSIBLE:
        current = Responsible.objects.filter(interaction=OuterRef("pk"), unassigned_at__isnull=True)
        # Взаимодействия без ответственного — в конце
        return (
            Subquery(current.values("manager__last_name")[:1]).asc(nulls_last=True),
            Subquery(current.values("manager__first_name")[:1]).asc(nulls_last=True),
            "-created_at",
            "pk",
        )
    return ("-created_at", "pk")


def _row_matches(row: ReportRow, spec: ReportSpec) -> bool:
    """Строка соответствует фильтрам состава: чужие продукты взаимодействия не попадают в отчёт."""
    if spec.directions and row.direction_id not in spec.directions:
        return False
    if spec.programs and row.program_id not in spec.programs:
        return False
    if spec.products and row.product_id not in spec.products:
        return False
    return True


def _user_name(user) -> str:
    return user.get_full_name() or user.get_username()


def _build_rows(ids: list, spec: ReportSpec) -> Iterator[ReportRow]:
    """Строит строки для пачки взаимодействий фиксированным числом запросов."""
    interactions = {
        interaction.pk: interaction
        for interaction in Interaction.objects.filter(pk__in=ids).select_related("university")
    }

    responsibles = {
        responsible.interaction_id: responsible
        for responsible in Responsible.objects.filter(
            interaction_id__in=ids, unassigned_at__isnull=True
        ).select_related("manager")
    }

    directions = defaultdict(list)
    for item in InteractionDirection.objects.filter(interaction_id__in=ids, is_active=True).select_related(
        "direction"
    ).order_by("added_at", "pk"):
        directions[item.interaction_id].append(item)

    programs = defaultdict(list)
    for item in InteractionProgram.objects.filter(interaction_id__in=ids, is_active=True).select_related(
        "program__direction"
    ).order_by("added_at", "pk"):
        programs[item.interaction_id].append(item)

    products = defaultdict(list)
    for item in InteractionProduct.objects.filter(interaction_id__in=ids, is_active=True).select_related(
        "product", "interaction_program__program__direction"
    ).order_by("added_at", "pk"):
        products[item.interaction_id].append(item)

    contracts = defaultdict(list)
    for contract in Contract.objects.filter(interaction_id__in=ids).order_by("created_at", "pk"):
        contracts[contract.interaction_id].append(contract)

    licenses = {
        license.interaction_product_id: license
        for license in License.objects.filter(
            interaction_product__interaction_id__in=ids, is_active=True
        ).order_by("created_at")
    }

    process_statuses = defaultdict(list)
    workflow_labels = dict(WorkflowInstance._meta.get_field("status").choices)
    for instance in WorkflowInstance.objects.filter(interaction_id__in=ids).select_related(
        "workflow"
    ).order_by("started_at", "pk"):
        process_statuses[instance.interaction_id].append(
            {
                "workflow_instance_id": str(instance.pk),
                "workflow": str(instance.workflow),
                "status": instance.status,
                "label": workflow_labels.get(instance.status, instance.status),
            }
        )

    # Актуальные этапы по контексту: (context_type, context_id) → этапы
    stages = defaultdict(list)
    for stage in StageInstance.objects.filter(
        workflow_instance__interaction_id__in=ids, status=ACTIVE_STAGE_STATUS
    ).select_related("stage", "workflow_instance").order_by("added_at", "pk"):
        context_id = stage.context_id
        if stage.context_type == StageInstanceContextType.INTERACTION and context_id is None:
            context_id = stage.workflow_instance.interaction_id
        stages[(stage.context_type, context_id)].append(
            Stage(id=stage.pk, name=stage.stage.name, context_type=stage.context_type)
        )

    for interaction_id in ids:
        interaction = interactions.get(interaction_id)
        if interaction is None:
            continue
        responsible = responsibles.get(interaction_id)
        interaction_contracts = contracts[interaction_id]
        interaction_directions = {item.direction_id: item for item in directions[interaction_id]}
        interaction_stages = stages.get((StageInstanceContextType.INTERACTION, interaction_id), ())

        def new_row() -> ReportRow:
            return ReportRow(
                interaction_id=interaction.pk,
                university_id=interaction.university_id,
                university=interaction.university.name if interaction.university else "",
                created_at=interaction.created_at,
                updated_at=interaction.updated_at,
                responsible_id=responsible.manager_id if responsible else None,
                responsible=_user_name(responsible.manager) if responsible else "",
                process_statuses=process_statuses[interaction_id],
                contract_numbers=[c.contract_number or f"Договор #{c.pk}" for c in interaction_contracts],
                contract_signed_at=[c.signed_at for c in interaction_contracts if c.signed_at],
            )

        def set_direction(row: ReportRow, direction) -> None:
            row.direction_id = direction.pk
            row.direction = direction.name
            interaction_direction = interaction_directions.get(direction.pk)
            if interaction_direction is not None:
                row.interaction_direction_id = interaction_direction.pk

        def set_program(row: ReportRow, interaction_program) -> None:
            row.program_id = interaction_program.program_id
            row.interaction_program_id = interaction_program.pk
            row.program = interaction_program.program.name
            set_direction(row, interaction_program.program.direction)

        def finish(row: ReportRow) -> ReportRow:
            row.active_stages = [
                *interaction_stages,
                *stages.get((StageInstanceContextType.DIRECTION, row.interaction_direction_id), ()),
                *stages.get((StageInstanceContextType.PROGRAM, row.interaction_program_id), ()),
                *stages.get((StageInstanceContextType.PRODUCT, row.interaction_product_id), ()),
            ]
            return row

        rows: list[ReportRow] = []
        covered_programs = set()
        covered_directions = set()

        for interaction_product in products[interaction_id]:
            row = new_row()
            row.product_id = interaction_product.product_id
            row.interaction_product_id = interaction_product.pk
            row.product = interaction_product.product.name
            if interaction_product.interaction_program is not None:
                set_program(row, interaction_product.interaction_program)
                covered_programs.add(interaction_product.interaction_program_id)
                covered_directions.add(row.direction_id)
            license = licenses.get(interaction_product.pk)
            if license is not None:
                row.license_status = "Подписана" if license.is_signed else "Не подписана"
                row.license_valid_until_year = license.valid_until_year
            rows.append(finish(row))

        for interaction_program in programs[interaction_id]:
            covered_directions.add(interaction_program.program.direction_id)
            if interaction_program.pk in covered_programs:
                continue
            row = new_row()
            set_program(row, interaction_program)
            rows.append(finish(row))

        for interaction_direction in directions[interaction_id]:
            if interaction_direction.direction_id in covered_directions:
                continue
            row = new_row()
            set_direction(row, interaction_direction.direction)
            rows.append(finish(row))

        if not rows:
            rows.append(finish(new_row()))

        for row in rows:
            if _row_matches(row, spec):
                yield row

