from django.db import migrations

# Тип уведомления → получатели по умолчанию (ответственному, руководителю). Остальные поля — значения по умолчанию модели.
DEFAULT_RECIPIENT_FLAGS = (
    ("action_deadline", True, False),
    ("stage_deadline", True, True),
    ("workflow_deadline", True, True),
    ("kam_assigned", True, False),
)


def create_default_settings(apps, schema_editor):
    """Создаёт по строке NotifySettings на каждый тип уведомления."""
    NotifySettings = apps.get_model("notifications", "NotifySettings")
    for notify_type, is_notify_responsible, is_notify_head in DEFAULT_RECIPIENT_FLAGS:
        NotifySettings.objects.get_or_create(
            notify_type=notify_type,
            defaults={"is_notify_responsible": is_notify_responsible, "is_notify_head": is_notify_head},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_notifysettings"),
    ]

    operations = [
        migrations.RunPython(create_default_settings, migrations.RunPython.noop),
    ]
