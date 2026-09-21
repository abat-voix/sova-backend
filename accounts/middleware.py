from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from mozilla_django_oidc.middleware import SessionRefresh


API_PATH_PREFIX = "/api/"


class ApiSessionRefresh(SessionRefresh):
    """
    Продление сессии OIDC, пригодное для запросов из браузерного кода.

    Базовый middleware при истёкшем id token отвечает редиректом на Keycloak с
    `prompt=none`. Для навигации это верно, но `fetch` идёт по такому редиректу
    сам и упирается в чужой origin без заголовков CORS — запрос падает с
    ошибкой CORS вместо внятного статуса.

    Поэтому запросам к API (ожидающим JSON, а не HTML) отдаётся `401` с кодом
    `session_expired`: `refresh_url` — адрес молчаливого продления,
    `login_url` — адрес полноценного входа, к которому клиент добавляет
    `?next=` со своей страницей. Навигация браузера по-прежнему получает
    редирект, чтобы Swagger UI и Django Admin работали как раньше.
    """

    def process_request(self, request: HttpRequest) -> HttpResponse | None:
        """Подменяет ответ базового middleware на JSON для запросов к API."""
        response = super().process_request(request)
        if response is None or not self.is_api_request(request):
            return response

        refresh_url = response.headers.get("refresh_url") or response.headers.get(
            "Location", ""
        )
        # Базовый middleware записал сюда путь API-запроса: после входа
        # пользователь оказался бы на JSON-ответе вместо страницы приложения
        request.session.pop("oidc_login_next", None)

        return JsonResponse(
            {
                "detail": _("Сессия истекла, требуется повторный вход."),
                "code": "session_expired",
                "refresh_url": refresh_url,
                "login_url": reverse("oidc_authentication_init"),
            },
            status=401,
        )

    @staticmethod
    def is_api_request(request: HttpRequest) -> bool:
        """Запрос к API — путь под `/api/` от клиента, которому нужен не HTML."""
        if not request.path.startswith(API_PATH_PREFIX):
            return False
        return "text/html" not in request.headers.get("Accept", "")
