from collections import defaultdict

from django.db import migrations
from django.db.models import ProtectedError, RestrictedError

# Ключи каталога и колонок импорта, которые сменились вместе с моделью вуза
CATALOG_TYPE_RENAMES = {"university": "organization"}
TARGET_FIELD_RENAMES = {"university": "organization", "university_contact": "organization_contact"}


def force_delete(queryset) -> None:
    """Удаляет записи вместе с теми, что ссылаются на них через PROTECT/RESTRICT (потоки, заявки, договоры)."""
    while queryset.exists():
        try:
            queryset.delete()
            return
        except (ProtectedError, RestrictedError) as error:
            blockers = error.protected_objects if isinstance(error, ProtectedError) else error.restricted_objects
            by_model = defaultdict(set)
            for obj in blockers:
                by_model[type(obj)].add(obj.pk)
            for model, pks in by_model.items():
                force_delete(model._default_manager.filter(pk__in=pks))


def rename_import_keys(apps, schema_editor) -> None:
    """Маппинги импорта каталогов: тип «university» и ключи колонок вуза теперь — «organization»."""
    mapping = apps.get_model("catalog", "CatalogImportMapping")
    for old, new in CATALOG_TYPE_RENAMES.items():
        mapping.objects.filter(catalog_type=old).update(catalog_type=new)
    for old, new in TARGET_FIELD_RENAMES.items():
        mapping.objects.filter(target_field=old).update(target_field=new)


def delete_legal_b2c_clients(apps, schema_editor) -> None:
    """
    B2C-клиент теперь только физлицо: юрлица удаляются вместе с их взаимодействиями, договорами, потоками и
    преподавателями. Обучающиеся остаются — они не принадлежат клиенту.
    """
    b2c_client = apps.get_model("catalog", "B2CClient")
    force_delete(b2c_client.objects.filter(kind="legal_entity"))


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0012_rename_university_to_organization"),
        ("interactions", "0017_rename_university_to_organization"),
        ("training", "0002_rename_university_to_organization"),
        ("processes", "0009_actionattachment_backfill_original_name"),
        ("messaging", "0004_conversation_created_by_conversation_interaction_and_more"),
        ("notifications", "0011_telegramlinktoken_and_more"),
        ("workflows", "0011_workflowstage_height_workflowstage_position_x_and_more"),
        ("reports", "0001_initial"),
        ("integrations", "0003_integrationmessage_mapping_result"),
    ]

    operations = [
        migrations.RunPython(rename_import_keys, migrations.RunPython.noop),
        migrations.RunPython(delete_legal_b2c_clients, migrations.RunPython.noop),
    ]
