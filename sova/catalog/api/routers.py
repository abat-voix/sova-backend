from rest_framework.routers import DefaultRouter

from sova.catalog.api import views

app_name = "catalog"

router = DefaultRouter()
router.register("vendors", views.VendorViewSet, basename="vendor")
router.register("it-directions", views.ITDirectionViewSet, basename="it-direction")
router.register("it-programs", views.ITProgramViewSet, basename="it-program")
router.register("it-products", views.ITProductViewSet, basename="it-product")
router.register("universities", views.UniversityViewSet, basename="university")
router.register("b2c-clients", views.B2CClientViewSet, basename="b2c-client")
router.register("contact-persons", views.ContactPersonViewSet, basename="contact-person")

urlpatterns = router.urls
