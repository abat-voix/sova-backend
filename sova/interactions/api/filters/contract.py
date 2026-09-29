from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import SearchFilterMixin, UUIDInFilter
from sova.interactions.models import Contract


class ContractFilter(SearchFilterMixin):
    """Фильтр договоров."""

    interaction__ids = UUIDInFilter(
        field_name="interaction",
        label=_("Взаимодействия"),
        help_text=_("Фильтр по списку ID взаимодействий через запятую"),
    )
    signed_at__gte = filters.DateFilter(
        field_name="signed_at",
        lookup_expr="gte",
        label=_("Подписан с"),
        help_text=_("Начало периода подписания, включительно (ГГГГ-ММ-ДД)"),
    )
    signed_at__lte = filters.DateFilter(
        field_name="signed_at",
        lookup_expr="lte",
        label=_("Подписан по"),
        help_text=_("Конец периода подписания, включительно (ГГГГ-ММ-ДД)"),
    )

    is_signed = filters.BooleanFilter(
        method="filter_is_signed",
        label=_("Подписан"),
        help_text=_("True — только подписанные договоры, false — ещё не подписанные"),
    )

    organization__ids = UUIDInFilter(
        field_name="organization",
        label=_("Организации"),
        help_text=_(
            "Фильтр по списку ID организаций через запятую; контрагент хранится и у договора без взаимодействия"
        ),
    )
    is_attached = filters.BooleanFilter(
        field_name="interaction",
        lookup_expr="isnull",
        exclude=True,
        label=_("Привязан к взаимодействию"),
        help_text=_(
            "False — договоры из реестра, по которым ещё не создано взаимодействие "
            "(см. attach-to-new-interaction); true — привязанные"
        ),
    )

    class Meta:
        model = Contract
        fields = ()
        exact_search_fields = ["contract_number"]

    def filter_is_signed(
        self,
        queryset: QuerySet,
        name: str,
        value: bool,
    ) -> QuerySet:
        """Фильтрует договоры по наличию даты подписания."""
        return queryset.filter(signed_at__isnull=not value)
