from sova.catalog.api.views.b2c_client import B2CClientViewSet
from sova.catalog.api.views.catalog_import import CatalogImportViewSet
from sova.catalog.api.views.contact_person import ContactPersonViewSet
from sova.catalog.api.views.direction import DirectionViewSet
from sova.catalog.api.views.import_mapping import CatalogImportMappingViewSet
from sova.catalog.api.views.product import ProductViewSet
from sova.catalog.api.views.program import ProgramViewSet
from sova.catalog.api.views.university import UniversityViewSet
from sova.catalog.api.views.vendor import VendorViewSet

__all__ = [
    "B2CClientViewSet",
    "CatalogImportMappingViewSet",
    "CatalogImportViewSet",
    "ContactPersonViewSet",
    "DirectionViewSet",
    "ProductViewSet",
    "ProgramViewSet",
    "UniversityViewSet",
    "VendorViewSet",
]
