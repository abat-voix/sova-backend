import json
import logging
import secrets

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from sova.notifications.services import telegram_webhook

logger = logging.getLogger("django")


@method_decorator(csrf_exempt, name="dispatch")
class TelegramWebhookView(APIView):
    """
    Webhook Telegram-бота (setWebhook): принимает update'ы и обрабатывает `/start <токен>`.

    Проверяет заголовок X-Telegram-Bot-Api-Secret-Token, который Telegram присылает
    с каждым запросом, если секрет был задан в setWebhook.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def post(self, request):
        expected = settings.TELEGRAM_WEBHOOK_SECRET
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not expected or not secrets.compare_digest(received, expected):
            return Response({"detail": "Invalid secret token"}, status=status.HTTP_403_FORBIDDEN)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Response({"detail": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(payload, dict):
            return Response({"detail": "Payload must be a JSON object"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = telegram_webhook.handle_update(payload)
        except Exception:
            # Не роняем webhook на непредвиденных данных от Telegram — иначе он будет повторять update бесконечно
            logger.exception("Ошибка обработки Telegram update")
            return Response(status=status.HTTP_200_OK)

        telegram_webhook.send_reply(result)
        return Response(status=status.HTTP_200_OK)
