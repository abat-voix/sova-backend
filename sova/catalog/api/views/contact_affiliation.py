from sova.catalog.api import filters, serializers
from sova.catalog.api.views.mixins import CatalogPolicyMixin
from sova.catalog.models import B2CClientContact, OrganizationContact, VendorContact
from sova.catalog.services import contact_affiliation_service
from sova.core.api.views import SovaBaseViewSet


class _ContactAffiliationViewSet(CatalogPolicyMixin, SovaBaseViewSet):
    """Связи человека с организациями: удаление — уход из организации (отвязка от активных взаимодействий)."""

    ordering_fields = ("contact__full_name", "position", "created_at", "updated_at")

    def perform_destroy(self, instance) -> None:
        """Удаление через сервис связей: отвязка от взаимодействий организации и уведомление КАМов."""
        contact_affiliation_service.delete(affiliation=instance, actor=self.request.user)


class OrganizationContactViewSet(_ContactAffiliationViewSet):
    """Связи контактных лиц с организациями: должность и способы связи. Доступны CRUD операции."""

    read_serializer_class = serializers.OrganizationContactSerializer
    serializer_class = serializers.WriteOrganizationContactSerializer
    queryset = OrganizationContact.objects.select_related("contact", "organization")
    search_fields = ("contact__full_name", "position", "organization__name")
    filterset_class = filters.OrganizationContactFilter


class B2CClientContactViewSet(_ContactAffiliationViewSet):
    """Связи контактных лиц с B2C-клиентами: должность и способы связи. Доступны CRUD операции."""

    read_serializer_class = serializers.B2CClientContactSerializer
    serializer_class = serializers.WriteB2CClientContactSerializer
    queryset = B2CClientContact.objects.select_related("contact", "b2c_client")
    search_fields = ("contact__full_name", "position", "b2c_client__full_name")
    filterset_class = filters.B2CClientContactFilter


class VendorContactViewSet(_ContactAffiliationViewSet):
    """Связи контактных лиц с вендорами: должность, способы связи и продукты. Доступны CRUD операции."""

    read_serializer_class = serializers.VendorContactSerializer
    serializer_class = serializers.WriteVendorContactSerializer
    queryset = VendorContact.objects.select_related("contact", "vendor").prefetch_related("products")
    search_fields = ("contact__full_name", "position", "vendor__name")
    filterset_class = filters.VendorContactFilter
