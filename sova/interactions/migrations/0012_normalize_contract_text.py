from django.db import migrations

from sova.core.text import normalize_text

# Поля, которые Contract теперь нормализует при сохранении (NormalizedTextFieldsMixin).
NORMALIZED_FIELDS = ("contract_number", "draft_manager_full_name", "draft_status")


def normalize_existing_values(apps, schema_editor) -> None:
    """Нормализует уже сохранённые номера договоров: импорт реестра сопоставляет их с нормализованным файлом."""
    contract_model = apps.get_model("interactions", "Contract")
    for contract in contract_model.objects.all().iterator():
        changed = []
        for field in NORMALIZED_FIELDS:
            value = getattr(contract, field)
            if isinstance(value, str) and normalize_text(value) != value:
                setattr(contract, field, normalize_text(value))
                changed.append(field)
        if changed:
            contract.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ("interactions", "0011_interaction_triad_headless"),
    ]

    operations = [
        migrations.RunPython(normalize_existing_values, migrations.RunPython.noop),
    ]
