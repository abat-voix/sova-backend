from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.interactions.models import License


class LicenseFilter(SearchFilterMixin):
    """Фильтр лицензий."""

    interaction__ids = UUIDInFilter(
        field_name="contract__interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий договоров через запятую"),
    )
    contract__ids = UUIDInFilter(
        field_name="contract",
        label=_("Договоры"),
        help_text=_("Фильтр по списку ID договоров через запятую"),
    )
    interaction_product__ids = UUIDInFilter(
        field_name="interaction_product",
        label=_("Продукты взаимодействия"),
        help_text=_("Фильтр по списку ID продуктов взаимодействия через запятую"),
    )
    it_product__ids = UUIDInFilter(
        field_name="interaction_product__it_product",
        label=_("ИТ-продукты"),
        help_text=_("Фильтр по списку ID каталожных ИТ-продуктов через запятую"),
    )
    valid_until_year__gte = filters.NumberFilter(
        field_name="valid_until_year",
        lookup_expr="gte",
        label=_("Действует до, не ранее"),
        help_text=_("Нижняя граница года окончания срока действия, включительно"),
    )
    valid_until_year__lte = filters.NumberFilter(
        field_name="valid_until_year",
        lookup_expr="lte",
        label=_("Действует до, не позднее"),
        help_text=_("Верхняя граница года окончания срока действия, включительно"),
    )
    signed_at__gte = filters.DateFilter(
        field_name="signed_at",
        lookup_expr="gte",
        label=_("Подписана с"),
        help_text=_("Начало периода подписания, включительно (ГГГГ-ММ-ДД)"),
    )
    signed_at__lte = filters.DateFilter(
        field_name="signed_at",
        lookup_expr="lte",
        label=_("Подписана по"),
        help_text=_("Конец периода подписания, включительно (ГГГГ-ММ-ДД)"),
    )

    class Meta:
        model = License
        fields = (
            "is_active",
            "is_signed",
            "valid_until_year",
        )
