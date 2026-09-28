from django.db.models import Exists, OuterRef, QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.catalog.api.filters.rank import RankFilterMixin
from sova.catalog.models import University
from sova.interactions.models import Interaction


class UniversityFilter(RankFilterMixin):
    """Фильтр вузов."""

    has_interactions = filters.BooleanFilter(
        method="filter_has_interactions",
        label=_("Наличие взаимодействий"),
        help_text=_("True — только вузы со взаимодействиями, false — без них"),
    )

    class Meta:
        model = University
        fields = ("is_active",)
        exact_search_fields = ["name", "inn", "external_code"]

    def filter_has_interactions(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Фильтрует вузы по наличию связанных взаимодействий."""
        has_interactions = Exists(Interaction.objects.filter(university=OuterRef("pk")))
        return queryset.filter(has_interactions if value else ~has_interactions)
