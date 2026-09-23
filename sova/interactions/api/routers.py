from rest_framework.routers import DefaultRouter

from sova.interactions.api import views

app_name = "interactions"

router = DefaultRouter()
router.register("interactions", views.InteractionViewSet, basename="interaction")
router.register("responsibles", views.ResponsibleViewSet, basename="responsible")
router.register("contracts", views.ContractViewSet, basename="contract")
router.register("contract-files", views.ContractFileViewSet, basename="contract-file")
router.register(
    "interaction-directions",
    views.InteractionDirectionViewSet,
    basename="interaction-direction",
)
router.register(
    "interaction-programs",
    views.InteractionProgramViewSet,
    basename="interaction-program",
)
router.register(
    "interaction-products",
    views.InteractionProductViewSet,
    basename="interaction-product",
)
router.register("licenses", views.LicenseViewSet, basename="license")

urlpatterns = router.urls
