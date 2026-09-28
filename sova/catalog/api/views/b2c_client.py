from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api import filters, serializers
from sova.catalog.api.views.mixins import CatalogPolicyMixin, CatalogRankMixin
from sova.catalog.models import B2CClient
from sova.catalog.services import b2c_client_address_service
from sova.core.api.views import SovaBaseViewSet


class B2CClientViewSet(CatalogPolicyMixin, CatalogRankMixin, SovaBaseViewSet):
    """
    B2C-клиенты — физические лица. Доступны CRUD операции. В карточке — открытая часть адреса; адрес регистрации
    целиком (`registration-address/`) — только администратору платформы, каждое обращение пишется в журнал.
    """

    read_serializer_class = serializers.B2CClientSerializer
    serializer_class = serializers.WriteB2CClientSerializer
    queryset = B2CClient.objects.select_related("address")
    ordering_fields = "__all__"
    search_fields = ("full_name", "inn", "email", "phone")
    filterset_class = filters.B2CClientFilter
    policy_actions = {
        **CatalogPolicyMixin.policy_actions,
        "registration_address": {
            "GET": Action.CATALOG_PERSONAL_DATA_READ,
            "PUT": Action.CATALOG_PERSONAL_DATA_UPDATE,
        },
    }

    @extend_schema(methods=["GET"], request=None, responses=serializers.B2CClientRegistrationAddressSerializer)
    @extend_schema(
        methods=["PUT"],
        request=serializers.B2CClientRegistrationAddressSerializer,
        responses=serializers.B2CClientRegistrationAddressSerializer,
    )
    @action(
        methods=["GET", "PUT"],
        detail=True,
        url_path="registration-address",
        serializer_class=serializers.B2CClientRegistrationAddressSerializer,
    )
    def registration_address(self, request, pk=None) -> Response:
        """Адрес регистрации целиком: просмотр и изменение улицы, дома, квартиры и индекса пишутся в журнал."""
        client = self.get_object()
        if request.method == "GET":
            address = b2c_client_address_service.read_personal(client=client, user=request.user, request=request)
            return Response(self.get_serializer(address).data)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        address = b2c_client_address_service.save_personal(
            client=client, values=serializer.validated_data, user=request.user, request=request
        )
        return Response(self.get_serializer(address).data)
