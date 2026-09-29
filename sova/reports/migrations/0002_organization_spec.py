from django.db import migrations


def migrate_specs(apps, schema_editor) -> None:
    """Параметры сохранённых отчётов: фильтр, колонка и сортировка по вузу теперь — по организации."""
    report_job = apps.get_model("reports", "ReportJob")
    for job in report_job.objects.all():
        spec = dict(job.spec)
        if "universities" in spec:
            spec["organizations"] = spec.pop("universities")
        if spec.get("ordering") in ("university", "-university"):
            spec["ordering"] = spec["ordering"].replace("university", "organization")
        if "columns" in spec:
            spec["columns"] = ["organization" if column == "university" else column for column in spec["columns"]]
        if spec != job.spec:
            job.spec = spec
            job.save(update_fields=["spec"])


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrate_specs, migrations.RunPython.noop),
    ]
