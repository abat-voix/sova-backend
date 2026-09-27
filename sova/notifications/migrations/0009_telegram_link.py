import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


def dedupe_telegram_chat_ids(apps, schema_editor):
    """
    Обнуляет повторяющиеся непустые telegram_chat_id перед добавлением уникального ограничения.

    Из каждой группы дублей оставляет значение только у самой старой записи (по created_at
    недоступен на NotificationProfile — используется id), остальным очищает поле. Если дублей
    нет, ничего не делает.
    """
    NotificationProfile = apps.get_model("notifications", "NotificationProfile")
    seen = set()
    duplicates_ids = []
    queryset = (
        NotificationProfile.objects.exclude(telegram_chat_id="")
        .order_by("id")
        .values_list("id", "telegram_chat_id")
    )
    for profile_id, chat_id in queryset:
        if chat_id in seen:
            duplicates_ids.append(profile_id)
        else:
            seen.add(chat_id)
    if duplicates_ids:
        NotificationProfile.objects.filter(id__in=duplicates_ids).update(telegram_chat_id="")


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("notifications", "0008_head_notify_settings_defaults"),
    ]

    operations = [
        migrations.RunPython(dedupe_telegram_chat_ids, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="notificationprofile",
            constraint=models.UniqueConstraint(
                condition=~Q(telegram_chat_id=""),
                fields=("telegram_chat_id",),
                name="unique_non_empty_telegram_chat_id",
            ),
        ),
        migrations.CreateModel(
            name="TelegramLinkToken",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Дата обновления")),
                ("expires_at", models.DateTimeField(verbose_name="Действителен до")),
                ("used_at", models.DateTimeField(blank=True, null=True, verbose_name="Использован")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="telegram_link_tokens",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Пользователь",
                    ),
                ),
            ],
            options={
                "verbose_name": "Токен привязки Telegram",
                "verbose_name_plural": "Токены привязки Telegram",
                "ordering": ["-created_at"],
            },
        ),
    ]
