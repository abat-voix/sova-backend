from django.utils.translation import gettext_lazy as _

from sova.catalog.models import ContactPerson
from sova.core.api.filters import SearchFilterMixin, UUIDInFilter


class ContactPersonFilter(SearchFilterMixin):
    """Фильтр контактных лиц."""

    university__ids = UUIDInFilter(
        field_name="university",
        label=_("Вузы"),
        help_text=_("Фильтр по списку ID вузов через запятую"),
    )
    b2c_client__ids = UUIDInFilter(
        field_name="b2c_client",
        label=_("B2C-клиенты"),
        help_text=_("Фильтр по списку ID B2C-клиентов через запятую"),
    )

    class Meta:
        model = ContactPerson
        fields = ("is_active",)
        exact_search_fields = ["full_name", "email"]
