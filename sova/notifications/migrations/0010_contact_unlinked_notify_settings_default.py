from django.db import migrations

NOTIFY_TYPE = "contact_unlinked"


def create_settings(apps, schema_editor):
    """
    Уведомление КАМов взаимодействия об отвязке контактного лица (человек ушёл из организации).

    Без строки настроек уведомление не отправляется; по умолчанию — ответственным КАМам, руководителю — нет.
    """
    NotifySettings = apps.get_model("notifications", "NotifySettings")
    NotifySettings.objects.get_or_create(
        notify_type=NOTIFY_TYPE,
        defaults={"is_notify_responsible": True, "is_notify_head": False},
    )


def delete_settings(apps, schema_editor):
    """Удаляет строку, созданную прямой миграцией."""
    NotifySettings = apps.get_model("notifications", "NotifySettings")
    NotifySettings.objects.filter(notify_type=NOTIFY_TYPE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0009_contact_unlinked_notify_type"),
    ]

    operations = [
        migrations.RunPython(create_settings, delete_settings),
    ]
