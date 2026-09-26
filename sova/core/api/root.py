from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView


# Разделы API: ключ ответа -> имя URL (корень роутера раздела или список)
API_SECTIONS = {
    "users": "users:user-list",
    "catalog": "catalog:api-root",
    "interactions": "interactions:api-root",
    "workflows": "workflows:api-root",
    "processes": "processes:api-root",
    "notifications": "notifications:api-root",
}


@extend_schema(exclude=True)
class ApiRootView(APIView):
    """
    Корень API — ссылки на все разделы.

    У каждого раздела свой `DefaultRouter` со своим корнем, поэтому общий
    `/api/` собирает их вместе.
    """

    def get(self, request: Request, format: str | None = None) -> Response:
        """Возвращает ссылки на корни разделов API."""
        return Response(
            {
                name: reverse(url_name, request=request, format=format)
                for name, url_name in API_SECTIONS.items()
            },
        )
