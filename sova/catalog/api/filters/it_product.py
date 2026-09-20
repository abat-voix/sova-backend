from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.catalog.models import ITProduct
from sova.core.api.filters import SearchFilterMixin, UUIDInFilter


class ITProductFilter(SearchFilterMixin):
    """
    Фильтр ИТ-продуктов.

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
    it_program__ids = UUIDInFilter(
        field_name="programs",
        distinct=True,
        label=_("ИТ-программы"),
        help_text=_("Фильтр по списку ID ИТ-программ через запятую"),
    )
    it_direction__ids = UUIDInFilter(
        field_name="programs__it_direction",
        distinct=True,
        label=_("ИТ-направления"),
        help_text=_(
            "Фильтр по списку ID ИТ-направлений через запятую; "
            "направление определяется по программам продукта",
        ),
    )

    class Meta:
        model = ITProduct
        fields = ("is_active",)
        exact_search_fields = ["name", "external_code"]
