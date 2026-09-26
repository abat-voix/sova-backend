from django.urls import include, path
from rest_framework.routers import SimpleRouter

from sova.integrations.api.views import (
    IntegrationEntityMetadataView,
    IntegrationEventsView,
    IntegrationMappingViewSet,
    IntegrationSystemsView,
)


router = SimpleRouter()
router.register("mappings", IntegrationMappingViewSet, basename="mapping")

app_name = "integrations"
urlpatterns = [
    path("v1/metadata/entities/", IntegrationEntityMetadataView.as_view(), name="entity-metadata"),
    path("v1/systems/", IntegrationSystemsView.as_view(), name="systems"),
    path("v1/", include(router.urls)),
    path("v1/<str:system_code>/events/", IntegrationEventsView.as_view(), name="events"),
]
