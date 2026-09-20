from django.db.models import Exists, OuterRef, QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.catalog.models import ITProduct, ITProgram
from sova.core.api.filters import SearchFilterMixin, UUIDInFilter


class ITProgramFilter(SearchFilterMixin):
    """Фильтр ИТ-программ."""

    it_direction__ids = UUIDInFilter(
        field_name="it_direction",
        label=_("ИТ-направления"),
        help_text=_("Фильтр по списку ID ИТ-направлений через запятую"),
    )

    has_products = filters.BooleanFilter(
        method="filter_has_products",
        label=_("Наличие продуктов"),
        help_text=_("True — только программы с ИТ-продуктами, false — без них"),
    )

    class Meta:
        model = ITProgram
        fields = ("is_active",)
        exact_search_fields = ["name"]

    def filter_has_products(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Фильтрует программы по наличию связанных ИТ-продуктов."""
        has_products = Exists(ITProduct.programs.through.objects.filter(
            itprogram_id=OuterRef("pk"),
        ))
        return queryset.filter(has_products if value else ~has_products)
