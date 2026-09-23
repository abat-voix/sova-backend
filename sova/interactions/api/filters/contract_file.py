from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters

from sova.core.api.filters import SearchFilterMixin
from sova.interactions.models import ContractFile


class ContractFileFilter(SearchFilterMixin):
    """Фильтр файлов договора."""

    contract = filters.UUIDFilter(
        field_name="contract",
        label=_("Договор"),
        help_text=_("ID договора"),
    )

    class Meta:
        model = ContractFile
        fields = ()
