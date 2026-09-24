from rest_framework.routers import DefaultRouter

from sova.notifications.api import views

app_name = "notifications"

router = DefaultRouter()
router.register("profiles", views.NotificationProfileViewSet, basename="notification-profile")
router.register("inbox", views.NotificationViewSet, basename="notification-inbox")

urlpatterns = router.urls
