from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

from django.test import SimpleTestCase
from django.utils import timezone

from sova.reports.services.presentation import build_report_presentation


def row(*, interaction_id, created_at, university, responsible_id=None):
    return SimpleNamespace(
        interaction_id=interaction_id,
        interaction_program_id=None,
        interaction_product_id=None,
        responsible_ids=[] if responsible_id is None else [responsible_id],
        responsible=[] if responsible_id is None else [f"Manager {responsible_id}"],
        university_id=uuid4(),
        university=university,
        process_statuses=[],
        active_stages=[],
        created_at=created_at,
    )


class ReportPresentationTest(SimpleTestCase):
    def test_returns_ready_metrics_charts_and_other_group(self):
        generated = timezone.make_aware(datetime(2026, 9, 1, 12))
        rows = [
            row(interaction_id=uuid4(), created_at=generated, university=f"University {i}", responsible_id=i)
            for i in range(10)
        ]

        result = build_report_presentation(rows, date_from=generated.date(), date_to=generated.date())

        self.assertEqual(result["metrics"][0]["display_value"], "10")
        self.assertEqual([chart["id"] for chart in result["charts"]], [
            "interactions_over_time",
            "by_responsible",
            "by_university",
            "by_process_status",
            "by_active_stage",
        ])
        responsible = result["charts"][1]["items"]
        self.assertEqual(len(responsible), 9)
        self.assertEqual(responsible[-1]["key"], "other")
        self.assertEqual(responsible[-1]["value"], 2)

    def test_fills_empty_periods_and_uses_english_labels(self):
        first = timezone.make_aware(datetime(2026, 9, 1, 12))
        last = timezone.make_aware(datetime(2026, 9, 3, 12))
        result = build_report_presentation(
            [row(interaction_id=uuid4(), created_at=first, university="A")],
            date_from=first.date(),
            date_to=last.date(),
            locale="en",
        )

        self.assertEqual(result["chart_meta"], {"locale": "en", "granularity": "day"})
        points = result["charts"][0]["points"]
        self.assertEqual([point["value"] for point in points], [1, 0, 0])
        self.assertEqual(result["metrics"][0]["label"], "Interactions")
