from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("accounts.api.routers")),
    path("api/auth/oidc/", include("mozilla_django_oidc.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/health/", include("health.urls")),
    path("api/catalog/", include("sova.catalog.api.routers")),
    path("api/interactions/", include("sova.interactions.api.routers")),
    path("api/workflows/", include("sova.workflows.api.routers")),
    path("api/processes/", include("sova.processes.api.routers")),
    path("api/notifications/", include("sova.notifications.api.routers")),
    path("api/messaging/", include("sova.messaging.api.routers")),
    path("api/reports/", include("sova.reports.api.routers")),
]
