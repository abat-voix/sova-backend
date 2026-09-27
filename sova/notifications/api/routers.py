from django.urls import path
from rest_framework.routers import DefaultRouter

from sova.notifications.api import views

app_name = "notifications"

router = DefaultRouter()
router.register("profiles", views.NotificationProfileViewSet, basename="notification-profile")
router.register("inbox", views.NotificationViewSet, basename="notification-inbox")

urlpatterns = router.urls + [
    path("telegram/", views.TelegramLinkView.as_view(), name="telegram-link"),
    path("telegram/webhook/", views.TelegramWebhookView.as_view(), name="telegram-webhook"),
]
