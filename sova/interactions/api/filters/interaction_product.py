from django.db.models import Exists, OuterRef, QuerySet
from django.utils.translation import gettext_lazy as _

from sova.catalog.models import Program
from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.interactions.models import InteractionProduct


class InteractionProductFilter(SearchFilterMixin):
    """
    Фильтр продуктов взаимодействия.

    Направление у продукта не хранится, а выводится через программы каталога.
    """

    interaction__ids = UUIDInFilter(
        field_name="interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий через запятую"),
    )
    interaction_program__ids = UUIDInFilter(
        field_name="interaction_program",
        label=_("Программы взаимодействия"),
        help_text=_("Фильтр по списку ID программ взаимодействия через запятую"),
    )
    product__ids = UUIDInFilter(
        field_name="product",
        label=_("Продукты"),
        help_text=_("Фильтр по списку ID продуктов через запятую"),
    )

    direction__ids = UUIDInFilter(
        method="filter_direction_ids",
        label=_("Направления"),
        help_text=_(
            "Фильтр по списку ID направлений через запятую; "
            "направление определяется по программам каталога продукта",
        ),
    )

    class Meta:
        model = InteractionProduct
        fields = ("is_active",)

    def filter_direction_ids(
        self,
        queryset: QuerySet,
        name: str,
        value: list,
    ) -> QuerySet:
        """Фильтрует продукты по направлениям программ каталога."""
        return queryset.filter(
            Exists(
                Program.objects.filter(
                    products=OuterRef("product"),
                    direction__in=value,
                ),
            ),
        )
