from django.urls import path

from sova.integrations.api.views import IntegrationEventsView


app_name = "integrations"
urlpatterns = [
    path("v1/<str:system_code>/events/", IntegrationEventsView.as_view(), name="events"),
]
