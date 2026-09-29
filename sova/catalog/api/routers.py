from rest_framework.routers import DefaultRouter

from sova.catalog.api import views

app_name = "catalog"

router = DefaultRouter()
router.register("vendors", views.VendorViewSet, basename="vendor")
router.register("directions", views.DirectionViewSet, basename="direction")
router.register("programs", views.ProgramViewSet, basename="program")
router.register("products", views.ProductViewSet, basename="product")
router.register("organizations", views.OrganizationViewSet, basename="organization")
router.register("b2c-clients", views.B2CClientViewSet, basename="b2c-client")
router.register("contact-persons", views.ContactPersonViewSet, basename="contact-person")
router.register("organization-contacts", views.OrganizationContactViewSet, basename="organization-contact")
router.register("b2c-client-contacts", views.B2CClientContactViewSet, basename="b2c-client-contact")
router.register("vendor-contacts", views.VendorContactViewSet, basename="vendor-contact")
router.register("imports", views.CatalogImportViewSet, basename="catalog-import")
router.register("import-mappings", views.CatalogImportMappingViewSet, basename="import-mapping")

urlpatterns = router.urls
