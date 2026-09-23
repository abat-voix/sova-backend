from django.db import migrations


def backfill_contract_files(apps, schema_editor):
    """
    Заводит по одной записи журнала для каждого договора с файлом, загруженным до появления
    `ContractFile` — иначе такой файл был бы виден в `Contract.file`, но не в истории.
    """
    Contract = apps.get_model("interactions", "Contract")
    ContractFile = apps.get_model("interactions", "ContractFile")
    for contract in Contract.objects.exclude(file=""):
        ContractFile.objects.create(
            contract=contract,
            file=contract.file.name,
            original_name=contract.file_name or contract.file.name,
            uploaded_at=contract.updated_at,
            uploaded_by=None,
        )


def noop_reverse(apps, schema_editor):
    """Обратной миграции не требуется: записи журнала не влияют на текущее состояние."""


class Migration(migrations.Migration):
    dependencies = [
        ("interactions", "0007_contractfile"),
    ]

    operations = [
        migrations.RunPython(backfill_contract_files, noop_reverse),
    ]
