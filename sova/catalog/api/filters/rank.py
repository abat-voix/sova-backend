from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import SearchFilterMixin


class RankFilterMixin(SearchFilterMixin):
    """
    Фильтры по месту в рейтинге каталога (`rank`, см. `CatalogRankingService`).

    Queryset должен быть аннотирован `rank` — это делает `CatalogRankMixin` вьюсета.
    """

    rank_max = filters.NumberFilter(
        field_name="rank",
        lookup_expr="lte",
        label=_("Место в рейтинге не ниже"),
        help_text=_("Например, 10 — топ-10; объекты без места не попадают"),
    )
    has_rank = filters.BooleanFilter(
        field_name="rank",
        lookup_expr="isnull",
        exclude=True,
        label=_("Наличие места в рейтинге"),
        help_text=_("True — только объекты с местом в рейтинге, false — без него"),
    )
