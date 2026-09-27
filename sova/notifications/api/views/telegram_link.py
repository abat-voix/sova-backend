from accounts.policy import Action
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from sova.notifications.api.serializers import TelegramLinkStatusSerializer
from sova.notifications.services import telegram_link


class TelegramLinkView(APIView):
    """Привязка Telegram текущего пользователя: статус/ссылка (GET) и отключение (DELETE)."""

    policy_action = Action.NOTIFICATIONS_USE

    def get(self, request):
        """Статус привязки; если Telegram не подключён — одноразовая ссылка на бота."""
        result = telegram_link.get_link_status(request.user)
        serializer = TelegramLinkStatusSerializer(result)
        return Response(serializer.data)

    def delete(self, request):
        """Отключает Telegram: очищает telegram_chat_id в профиле пользователя."""
        telegram_link.disconnect(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
