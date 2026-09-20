from django.db.models import Exists, OuterRef, QuerySet
from django.utils.translation import gettext_lazy as _

from sova.catalog.models import ITProgram
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
    it_product__ids = UUIDInFilter(
        field_name="it_product",
        label=_("ИТ-продукты"),
        help_text=_("Фильтр по списку ID ИТ-продуктов через запятую"),
    )

    it_direction__ids = UUIDInFilter(
        method="filter_it_direction_ids",
        label=_("ИТ-направления"),
        help_text=_(
            "Фильтр по списку ID ИТ-направлений через запятую; "
            "направление определяется по программам каталога продукта",
        ),
    )

    class Meta:
        model = InteractionProduct
        fields = ("is_active",)

    def filter_it_direction_ids(
        self,
        queryset: QuerySet,
        name: str,
        value: list,
    ) -> QuerySet:
        """Фильтрует продукты по направлениям программ каталога."""
        return queryset.filter(
            Exists(
                ITProgram.objects.filter(
                    it_products=OuterRef("it_product"),
                    it_direction__in=value,
                ),
            ),
        )
