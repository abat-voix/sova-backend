from sova.catalog.api import filters, serializers
from sova.catalog.models import ContactPerson
from sova.core.api.views import SovaBaseViewSet
from sova.catalog.api.views.mixins import CatalogPolicyMixin


class ContactPersonViewSet(CatalogPolicyMixin, SovaBaseViewSet):
    """Контактные лица вузов и B2C-клиентов. Доступны CRUD операции."""

    read_serializer_class = serializers.ContactPersonSerializer
    serializer_class = serializers.WriteContactPersonSerializer
    queryset = ContactPerson.objects.select_related("university", "b2c_client")
    ordering_fields = "__all__"
    search_fields = ("full_name", "position", "email", "phone")
    filterset_class = filters.ContactPersonFilter
