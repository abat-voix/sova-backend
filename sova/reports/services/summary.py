"""Статистика отчёта: считается из тех же строк, что и предпросмотр."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sova.reports.services.dataset import ReportRow

NO_RESPONSIBLE = "Без ответственного"
NO_PROCESS = "Без процесса"
NO_ACTIVE_STAGE = "Нет актуального этапа"


def build_summary(rows: Iterable[ReportRow]) -> dict:
    """
    Агрегаты по уникальным `Interaction.id`.

    Взаимодействие с несколькими продуктами даёт несколько строк, но в распределениях
    считается один раз в каждой группе; число строк, программ и продуктов — отдельно.
    Взаимодействие с несколькими КАМами входит в группу каждого из них, поэтому сумма
    `by_responsible` может превышать `interactions_count`.
    """
    interactions = set()
    programs = set()
    products = set()
    rows_count = 0
    by_responsible = defaultdict(set)
    responsible_names = {}
    by_organization = defaultdict(set)
    organization_names = {}
    by_process_status = defaultdict(set)
    process_labels = {}
    by_stage = defaultdict(set)

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
        by_organization[row.organization_id].add(row.interaction_id)
        organization_names[row.organization_id] = row.organization

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

    def distribution(groups, key_name, labels):
        items = [
            {key_name: None if key is None else str(key), "label": labels(key), "interactions": len(ids)}
            for key, ids in groups.items()
        ]
        return sorted(items, key=lambda item: (-item["interactions"], item["label"]))

    return {
        "interactions_count": len(interactions),
        "rows_count": rows_count,
        "programs_count": len(programs),
        "products_count": len(products),
        "by_responsible": distribution(by_responsible, "id", responsible_names.__getitem__),
        "by_organization": distribution(by_organization, "id", organization_names.__getitem__),
        "by_process_status": distribution(by_process_status, "status", process_labels.__getitem__),
        "by_active_stage": distribution(
            by_stage, "stage", lambda key: NO_ACTIVE_STAGE if key is None else key
        ),
    }
