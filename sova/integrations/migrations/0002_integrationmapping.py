import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("integrations", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="IntegrationMapping",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название")),
                ("system", models.CharField(max_length=50, verbose_name="Система")),
                ("event_type", models.CharField(max_length=100, verbose_name="Тип события")),
                ("direction", models.CharField(choices=[("incoming", "Входящее"), ("outgoing", "Исходящее")], max_length=8, verbose_name="Направление")),
                ("entity", models.CharField(max_length=100, verbose_name="Сущность CRM")),
                ("is_active", models.BooleanField(default=False, verbose_name="Активен")),
                ("version", models.PositiveIntegerField(default=1, verbose_name="Версия")),
                ("rules", models.JSONField(default=list, verbose_name="Правила")),
            ],
            options={"verbose_name": "маппинг интеграции", "verbose_name_plural": "маппинги интеграций", "ordering": ("-updated_at", "name")},
        ),
    ]
