from django.db import migrations

TARGET_FIELD_RENAMES = {"university": "organization"}


def migrate_mappings(apps, schema_editor) -> None:
    """
    Сущность «university» стала «organization», поле взаимодействия `university` — `organization`. У B2C-клиента
    больше нет типа (он всегда физлицо), поэтому правила на поле `kind` убираются.
    """
    mapping_model = apps.get_model("integrations", "IntegrationMapping")
    mapping_model.objects.filter(entity="university").update(entity="organization")
    for mapping in mapping_model.objects.all():
        rules = []
        for rule in mapping.rules:
            target = rule.get("targetField")
            if mapping.entity == "b2c_client" and target == "kind":
                continue
            rules.append({**rule, "targetField": TARGET_FIELD_RENAMES.get(target, target)})
        if rules != mapping.rules:
            mapping.rules = rules
            mapping.save(update_fields=["rules"])


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0003_integrationmessage_mapping_result"),
    ]

    operations = [
        migrations.RunPython(migrate_mappings, migrations.RunPython.noop),
    ]
