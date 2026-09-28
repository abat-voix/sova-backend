from django.db.models import Exists, OuterRef, QuerySet
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api import filters, serializers
from sova.catalog.api.views.mixins import CatalogPolicyMixin, CatalogRankMixin
from sova.catalog.models import Organization
from sova.catalog.services import organization_address_service
from sova.core.api.views import SovaBaseViewSet
from sova.interactions.models import Interaction


class OrganizationViewSet(CatalogPolicyMixin, CatalogRankMixin, SovaBaseViewSet):
    """Организации. Доступны CRUD операции."""

    read_serializer_class = serializers.OrganizationSerializer
    serializer_class = serializers.WriteOrganizationSerializer
    queryset = Organization.objects.prefetch_related("addresses")
    ordering_fields = "__all__"
    search_fields = ("short_name", "name", "inn", "external_code", "email")
    filterset_class = filters.OrganizationFilter
    policy_actions = {**CatalogPolicyMixin.policy_actions, "map_points": Action.CATALOG_READ}

    def get_queryset(self) -> QuerySet[Organization]:
        """Добавляет флаг наличия взаимодействий одним подзапросом, а не запросом на каждую организацию."""
        return super().get_queryset().annotate(
            has_interactions=Exists(Interaction.objects.filter(organization=OuterRef("pk"))),
        ).order_by(
            "-has_interactions",
            "name",
        )

    @action(
        detail=False,
        methods=("get",),
        serializer_class=serializers.OrganizationMapPointSerializer,
        pagination_class=None,
        url_path="map",
    )
    def map_points(self, request) -> Response:
        """
        Организации с координатами в облегчённом формате карты. Точка — по фактическому адресу, а если у него нет
        координат, — по юридическому.
        """
        queryset = organization_address_service.with_coordinates(
            self.filter_queryset(self.get_queryset()).prefetch_related(None).only("id")
        ).filter(lat__isnull=False, lon__isnull=False)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
