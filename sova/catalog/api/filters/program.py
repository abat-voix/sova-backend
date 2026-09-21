from django.db.models import Exists, OuterRef, QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.catalog.models import Product, Program
from sova.core.api.filters import SearchFilterMixin, UUIDInFilter


class ProgramFilter(SearchFilterMixin):
    """Фильтр программ."""

    direction__ids = UUIDInFilter(
        field_name="direction",
        label=_("Направления"),
        help_text=_("Фильтр по списку ID направлений через запятую"),
    )

    has_products = filters.BooleanFilter(
        method="filter_has_products",
        label=_("Наличие продуктов"),
        help_text=_("True — только программы с продуктами, false — без них"),
    )

    class Meta:
        model = Program
        fields = ("is_active",)
        exact_search_fields = ["name"]

    def filter_has_products(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Фильтрует программы по наличию связанных продуктов."""
        has_products = Exists(Product.programs.through.objects.filter(
            program_id=OuterRef("pk"),
        ))
        return queryset.filter(has_products if value else ~has_products)
