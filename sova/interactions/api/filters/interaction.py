from django.db.models import Exists, OuterRef, QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import NumberInFilter, SearchFilterMixin, UUIDInFilter
from sova.interactions.models import (
    Interaction,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    Responsible,
)


class InteractionFilter(SearchFilterMixin):
    """
    Фильтр взаимодействий.

    Фильтры по направлениям, программам и продуктам учитывают только активные
    записи состава взаимодействия и реализованы через Exists — без join'ов,
    которые задваивали бы строки и счётчики в списке.
    """

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
    created_at__gte = filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__gte",
        label=_("Создано с"),
        help_text=_("Начало периода по дате создания, включительно (ГГГГ-ММ-ДД)"),
    )
    created_at__lte = filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__lte",
        label=_("Создано по"),
        help_text=_("Конец периода по дате создания, включительно (ГГГГ-ММ-ДД)"),
    )

    it_direction__ids = UUIDInFilter(
        method="filter_it_direction_ids",
        label=_("ИТ-направления"),
        help_text=_("Взаимодействия с указанными активными ИТ-направлениями, ID через запятую"),
    )
    it_program__ids = UUIDInFilter(
        method="filter_it_program_ids",
        label=_("ИТ-программы"),
        help_text=_("Взаимодействия с указанными активными ИТ-программами, ID через запятую"),
    )
    it_product__ids = UUIDInFilter(
        method="filter_it_product_ids",
        label=_("ИТ-продукты"),
        help_text=_("Взаимодействия с указанными активными ИТ-продуктами, ID через запятую"),
    )
    manager__ids = NumberInFilter(
        method="filter_manager_ids",
        label=_("Ответственные менеджеры"),
        help_text=_("Только по действующему ответственному, ID пользователей через запятую"),
    )

    class Meta:
        model = Interaction
        fields = ("is_active",)

    def filter_it_direction_ids(
        self,
        queryset: QuerySet,
        name: str,
        value: list,
    ) -> QuerySet:
        """Фильтрует взаимодействия по активным ИТ-направлениям."""
        return queryset.filter(
            Exists(
                InteractionDirection.objects.filter(
                    interaction=OuterRef("pk"),
                    it_direction__in=value,
                    is_active=True,
                ),
            ),
        )

    def filter_it_program_ids(
        self,
        queryset: QuerySet,
        name: str,
        value: list,
    ) -> QuerySet:
        """Фильтрует взаимодействия по активным ИТ-программам."""
        return queryset.filter(
            Exists(
                InteractionProgram.objects.filter(
                    interaction=OuterRef("pk"),
                    it_program__in=value,
                    is_active=True,
                ),
            ),
        )

    def filter_it_product_ids(
        self,
        queryset: QuerySet,
        name: str,
        value: list,
    ) -> QuerySet:
        """Фильтрует взаимодействия по активным ИТ-продуктам."""
        return queryset.filter(
            Exists(
                InteractionProduct.objects.filter(
                    interaction=OuterRef("pk"),
                    it_product__in=value,
                    is_active=True,
                ),
            ),
        )

    def filter_manager_ids(
        self,
        queryset: QuerySet,
        name: str,
        value: list,
    ) -> QuerySet:
        """Фильтрует взаимодействия по действующему ответственному менеджеру."""
        return queryset.filter(
            Exists(
                Responsible.objects.filter(
                    interaction=OuterRef("pk"),
                    manager__in=value,
                    unassigned_at__isnull=True,
                ),
            ),
        )
