import os

from django.db import migrations


def backfill_file_name(apps, schema_editor):
    """Заполняет `file_name` у договоров с файлом, загруженным до появления этого поля."""
    Contract = apps.get_model("interactions", "Contract")
    for contract in Contract.objects.exclude(file="").filter(file_name=""):
        contract.file_name = os.path.basename(contract.file.name)
        contract.save(update_fields=["file_name"])


def noop_reverse(apps, schema_editor):
    """Обратной миграции не требуется: `file_name` — производное поле."""


class Migration(migrations.Migration):
    dependencies = [
        ("interactions", "0005_contract_file_name_alter_contract_file"),
    ]

    operations = [
        migrations.RunPython(backfill_file_name, noop_reverse),
    ]
