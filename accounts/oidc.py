import logging
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView

logger = logging.getLogger(__name__)


class SovaOIDCAuthenticationCallbackView(OIDCAuthenticationCallbackView):
    """
    Возврат из Keycloak, устойчивый к повторному обращению.

    Библиотечная реализация поднимает `SuspiciousOperation`, если `state` из
    query-параметров не найден в `request.session["oidc_states"]` — например,
    когда браузер повторяет запрос к callback (двойной сабмит, предзагрузка
    ссылки, возврат по истории) уже после того, как первый заход удалил
    использованный `state`. Пользователь в таком случае получает голую
    страницу с 400 вместо возврата в приложение.
    """

    def get(self, request):
        try:
            return super().get(request)
        except SuspiciousOperation:
            logger.warning(
                "OIDC callback повторён или state устарел — возвращаем на вход",
                exc_info=True,
            )
            return self.login_failure()


def provider_logout_url(request) -> str:
    params = {"post_logout_redirect_uri": f"{settings.APP_PUBLIC_URL}/"}
    id_token = request.session.get("oidc_id_token")
    if id_token:
        params["id_token_hint"] = id_token
    else:
        params["client_id"] = settings.KEYCLOAK_CLIENT_ID

    endpoint = (
        f"{settings.KEYCLOAK_PUBLIC_REALM_URL}/protocol/openid-connect/logout"
    )
    return f"{endpoint}?{urlencode(params)}"
