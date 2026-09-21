from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.models import Contract


class ContractViewSet(SovaBaseViewSet):
    """Договоры. Доступны CRUD операции; файл договора передаётся как multipart."""

    read_serializer_class = serializers.ContractSerializer
    serializer_class = serializers.WriteContractSerializer
    queryset = Contract.objects.select_related(
        "interaction__university",
        "interaction__b2c_client",
    )
    ordering_fields = "__all__"
    search_fields = ("contract_number",)
    filterset_class = filters.ContractFilter
