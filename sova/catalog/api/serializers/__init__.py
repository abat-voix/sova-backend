from sova.catalog.api.serializers.b2c_client import (
    B2CClientSerializer,
    B2CClientShortSerializer,
    WriteB2CClientSerializer,
)
from sova.catalog.api.serializers.catalog_import import (
    CatalogImportErrorSerializer,
    CatalogImportResultSerializer,
    CatalogImportRowErrorSerializer,
    CatalogImportSerializer,
)
from sova.catalog.api.serializers.contact_person import (
    ContactPersonSerializer,
    WriteContactPersonSerializer,
)
from sova.catalog.api.serializers.direction import (
    DirectionSerializer,
    DirectionShortSerializer,
    WriteDirectionSerializer,
)
from sova.catalog.api.serializers.import_mapping import (
    CatalogImportFieldSerializer,
    CatalogImportFieldsQuerySerializer,
    CatalogImportMappingSerializer,
    WriteCatalogImportMappingSerializer,
)
from sova.catalog.api.serializers.product import (
    ProductSerializer,
    ProductShortSerializer,
    WriteProductSerializer,
)
from sova.catalog.api.serializers.program import (
    ProgramSerializer,
    ProgramShortSerializer,
    WriteProgramSerializer,
)
from sova.catalog.api.serializers.university import (
    UniversityMapPointSerializer,
    UniversitySerializer,
    UniversityShortSerializer,
    WriteUniversitySerializer,
)
from sova.catalog.api.serializers.vendor import (
    VendorSerializer,
    VendorShortSerializer,
    WriteVendorSerializer,
)

__all__ = [
    "B2CClientSerializer",
    "B2CClientShortSerializer",
    "CatalogImportErrorSerializer",
    "CatalogImportFieldSerializer",
    "CatalogImportFieldsQuerySerializer",
    "CatalogImportMappingSerializer",
    "CatalogImportResultSerializer",
    "CatalogImportRowErrorSerializer",
    "CatalogImportSerializer",
    "ContactPersonSerializer",
    "DirectionSerializer",
    "DirectionShortSerializer",
    "ProductSerializer",
    "ProductShortSerializer",
    "ProgramSerializer",
    "ProgramShortSerializer",
    "UniversitySerializer",
    "UniversityMapPointSerializer",
    "UniversityShortSerializer",
    "VendorSerializer",
    "VendorShortSerializer",
    "WriteB2CClientSerializer",
    "WriteCatalogImportMappingSerializer",
    "WriteContactPersonSerializer",
    "WriteDirectionSerializer",
    "WriteProductSerializer",
    "WriteProgramSerializer",
    "WriteUniversitySerializer",
    "WriteVendorSerializer",
]
