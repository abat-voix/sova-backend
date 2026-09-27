import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    """
    Регистрирует webhook Telegram-бота через Bot API setWebhook.

    Разово запускается при деплое/смене TELEGRAM_WEBHOOK_SECRET или домена.
    URL webhook'а не хранится в settings — эндпоинт публичный
    (`/api/notifications/telegram/webhook/`), меняется только адрес бэкенда.
    """

    help = "Регистрирует webhook бота: POST setWebhook с адресом /api/notifications/telegram/webhook/."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--base-url",
            required=True,
            help="Публичный адрес бэкенда, например https://sova.example.com",
        )

    def handle(self, *args, **options) -> None:
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("TELEGRAM_BOT_TOKEN не задан")
        if not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError("TELEGRAM_WEBHOOK_SECRET не задан")

        webhook_url = f"{options['base_url'].rstrip('/')}/api/notifications/telegram/webhook/"
        response = requests.post(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook",
            data={
                "url": webhook_url,
                "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
                "allowed_updates": '["message"]',
            },
            timeout=settings.NOTIFICATION_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise CommandError(f"Telegram отказал: {result}")
        self.stdout.write(self.style.SUCCESS(f"Webhook зарегистрирован: {webhook_url}"))
