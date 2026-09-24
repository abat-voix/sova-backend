from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0005_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="notifysettings",
            name="is_channel_system",
            field=models.BooleanField(default=True, verbose_name="В системе"),
        ),
        migrations.RemoveConstraint(
            model_name="deadlinedelivery",
            name="unique_deadline_delivery",
        ),
        # Строки журнала до поканального учёта считаем доставленными по email
        migrations.AddField(
            model_name="deadlinedelivery",
            name="channel",
            field=models.CharField(
                choices=[("email", "Email"), ("telegram", "Telegram"), ("max", "MAX"), ("system", "В системе")],
                default="email",
                max_length=20,
                verbose_name="Канал",
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="deadlinedelivery",
            constraint=models.UniqueConstraint(
                fields=("notify_type", "event", "object_id", "deadline", "recipient", "channel"),
                name="unique_deadline_delivery",
            ),
        ),
    ]
