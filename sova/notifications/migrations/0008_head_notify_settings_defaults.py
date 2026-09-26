from django.db import migrations

# Уведомления о смене руководителя КАМа: по умолчанию и КАМу, и руководителю
HEAD_NOTIFY_TYPES = ("head_assigned", "head_unassigned")


def create_head_settings(apps, schema_editor):
    """Создаёт строки NotifySettings для назначения и снятия руководителя."""
    NotifySettings = apps.get_model("notifications", "NotifySettings")
    for notify_type in HEAD_NOTIFY_TYPES:
        NotifySettings.objects.get_or_create(
            notify_type=notify_type,
            defaults={"is_notify_responsible": True, "is_notify_head": True},
        )


def delete_head_settings(apps, schema_editor):
    """Удаляет строки, созданные прямой миграцией."""
    NotifySettings = apps.get_model("notifications", "NotifySettings")
    NotifySettings.objects.filter(notify_type__in=HEAD_NOTIFY_TYPES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0007_head_notify_types"),
    ]

    operations = [
        migrations.RunPython(create_head_settings, delete_head_settings),
    ]
