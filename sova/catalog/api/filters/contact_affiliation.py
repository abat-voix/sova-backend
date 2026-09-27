from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.catalog.models import B2CClientContact, UniversityContact, VendorContact
from sova.core.api.filters import UUIDInFilter


class UniversityContactFilter(filters.FilterSet):
    """Фильтр связей с вузами."""

    university__ids = UUIDInFilter(field_name="university", label=_("Вузы"))
    contact__is_active = filters.BooleanFilter(field_name="contact__is_active", label=_("Контактное лицо активно"))

    class Meta:
        model = UniversityContact
        fields = ("contact",)


class B2CClientContactFilter(filters.FilterSet):
    """Фильтр связей с B2C-клиентами."""

    b2c_client__ids = UUIDInFilter(field_name="b2c_client", label=_("B2C-клиенты"))
    contact__is_active = filters.BooleanFilter(field_name="contact__is_active", label=_("Контактное лицо активно"))

    class Meta:
        model = B2CClientContact
        fields = ("contact",)


class VendorContactFilter(filters.FilterSet):
    """Фильтр связей с вендорами."""

    vendor__ids = UUIDInFilter(field_name="vendor", label=_("Вендоры"))
    product__ids = UUIDInFilter(field_name="products", distinct=True, label=_("Продукты"))
    contact__is_active = filters.BooleanFilter(field_name="contact__is_active", label=_("Контактное лицо активно"))

    class Meta:
        model = VendorContact
        fields = ("contact",)
