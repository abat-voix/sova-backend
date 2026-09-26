from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="IntegrationMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("system", models.CharField(max_length=50, verbose_name="Система")),
                ("direction", models.CharField(choices=[("incoming", "Входящее"), ("outgoing", "Исходящее")], max_length=8, verbose_name="Направление")),
                ("event_type", models.CharField(default="generic.received", max_length=100, verbose_name="Тип события")),
                ("external_id", models.CharField(blank=True, max_length=255, verbose_name="Внешний ID")),
                ("correlation_id", models.UUIDField(default=uuid.uuid4, verbose_name="Correlation ID")),
                ("payload", models.JSONField(verbose_name="Payload")),
                ("status", models.CharField(choices=[("pending", "Ожидает обработки"), ("processing", "Обрабатывается"), ("processed", "Обработано"), ("retry", "Повтор"), ("failed", "Ошибка"), ("ignored", "Игнорировано")], default="pending", max_length=16, verbose_name="Статус")),
                ("attempts", models.PositiveSmallIntegerField(default=0, verbose_name="Попыток")),
                ("next_retry_at", models.DateTimeField(blank=True, null=True, verbose_name="Следующая попытка")),
                ("last_error", models.TextField(blank=True, verbose_name="Последняя ошибка")),
                ("processed_at", models.DateTimeField(blank=True, null=True, verbose_name="Обработано")),
            ],
            options={
                "verbose_name": "Интеграционное сообщение",
                "verbose_name_plural": "Интеграционные сообщения",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="integrationmessage",
            constraint=models.UniqueConstraint(condition=~models.Q(("external_id", "")), fields=("system", "direction", "external_id"), name="integration_message_external_id_uniq"),
        ),
        migrations.AddIndex(model_name="integrationmessage", index=models.Index(fields=["status", "next_retry_at"], name="integration_status_retry_idx")),
        migrations.AddIndex(model_name="integrationmessage", index=models.Index(fields=["system", "direction", "created_at"], name="integration_system_dir_idx")),
        migrations.AddIndex(model_name="integrationmessage", index=models.Index(fields=["correlation_id"], name="integration_correlation_idx")),
    ]
