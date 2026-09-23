import os

from django.db import migrations


def backfill_original_name(apps, schema_editor):
    """Заполняет `original_name` у вложений, загруженных до появления этого поля."""
    ActionAttachment = apps.get_model("processes", "ActionAttachment")
    for attachment in ActionAttachment.objects.exclude(file="").filter(original_name=""):
        attachment.original_name = os.path.basename(attachment.file.name)
        attachment.save(update_fields=["original_name"])


def noop_reverse(apps, schema_editor):
    """Обратной миграции не требуется: `original_name` — производное поле."""


class Migration(migrations.Migration):
    dependencies = [
        ("processes", "0008_actionattachment_content_type_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_original_name, noop_reverse),
    ]
