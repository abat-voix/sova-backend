from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.catalog.api.filters.rank import RankFilterMixin
from sova.catalog.models import Product
from sova.core.api.filters import UUIDInFilter


class ProductFilter(RankFilterMixin):
    """
    Фильтр продуктов.

    Направление у продукта не хранится, а выводится через его программы,
    поэтому фильтры по направлениям и программам идут по M2M и используют distinct.
    """

    vendor__ids = UUIDInFilter(
        field_name="vendor",
        label=_("Вендоры"),
        help_text=_("Фильтр по списку ID вендоров через запятую"),
    )
    vendor__isnull = filters.BooleanFilter(
        field_name="vendor",
        lookup_expr="isnull",
        label=_("Отсутствие вендора"),
        help_text=_("True — продукты без вендора, false — с вендором"),
    )
    program__ids = UUIDInFilter(
        field_name="programs",
        distinct=True,
        label=_("Программы"),
        help_text=_("Фильтр по списку ID программ через запятую"),
    )
    direction__ids = UUIDInFilter(
        field_name="programs__direction",
        distinct=True,
        label=_("Направления"),
        help_text=_(
            "Фильтр по списку ID направлений через запятую; "
            "направление определяется по программам продукта",
        ),
    )

    class Meta:
        model = Product
        fields = ("is_active",)
        exact_search_fields = ["name", "external_code"]
