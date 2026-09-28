from django.utils.translation import gettext_lazy as _

from sova.catalog.models import ContactPerson
from sova.core.api.filters import SearchFilterMixin, UUIDInFilter


class ContactPersonFilter(SearchFilterMixin):
    """Фильтр контактных лиц: по организациям их связей (человек со связью с любой из указанных)."""

    organization__ids = UUIDInFilter(
        field_name="organization_links__organization",
        distinct=True,
        label=_("Организации"),
        help_text=_("Фильтр по списку ID организаций через запятую"),
    )
    b2c_client__ids = UUIDInFilter(
        field_name="b2c_client_links__b2c_client",
        distinct=True,
        label=_("B2C-клиенты"),
        help_text=_("Фильтр по списку ID B2C-клиентов через запятую"),
    )
    vendor__ids = UUIDInFilter(
        field_name="vendor_links__vendor",
        distinct=True,
        label=_("Вендоры"),
        help_text=_("Фильтр по списку ID вендоров через запятую"),
    )
    product__ids = UUIDInFilter(
        field_name="vendor_links__products",
        distinct=True,
        label=_("Продукты"),
        help_text=_("Контакты вендоров, отвечающие за продукты (список ID через запятую)"),
    )

    class Meta:
        model = ContactPerson
        fields = ("is_active",)
        exact_search_fields = ["full_name", "email", "telegram"]
