from rest_framework.routers import DefaultRouter

from accounts.api.views import UserViewSet

app_name = "users"

router = DefaultRouter()
# Корень /api/ — общий, см. sova.core.api.root.ApiRootView
router.include_root_view = False
router.register("users", UserViewSet, basename="user")

urlpatterns = router.urls
