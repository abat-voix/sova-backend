from django.db.models import Exists, OuterRef, QuerySet
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api import filters, serializers
from sova.catalog.api.views.mixins import CatalogPolicyMixin
from sova.catalog.models import University
from sova.core.api.views import SovaBaseViewSet
from sova.interactions.models import Interaction


class UniversityViewSet(CatalogPolicyMixin, SovaBaseViewSet):
    """Вузы. Доступны CRUD операции."""

    read_serializer_class = serializers.UniversitySerializer
    serializer_class = serializers.WriteUniversitySerializer
    queryset = University.objects.all()
    ordering_fields = "__all__"
    search_fields = ("short_name", "name", "inn", "external_code", "email")
    filterset_class = filters.UniversityFilter
    policy_actions = {**CatalogPolicyMixin.policy_actions, "map_points": Action.CATALOG_READ}

    def get_queryset(self) -> QuerySet[University]:
        """Добавляет флаг наличия взаимодействий одним подзапросом, а не запросом на каждый вуз."""
        return super().get_queryset().annotate(
            has_interactions=Exists(Interaction.objects.filter(university=OuterRef("pk"))),
        ).order_by(
            "-has_interactions",
            "name",
        )

    def perform_create(self, serializer: serializers.WriteUniversitySerializer) -> None:
        """Пересоздание инстанса через аннотированный queryset для read-ответа."""
        super().perform_create(serializer)
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)

    @action(
        detail=False,
        methods=("get",),
        serializer_class=serializers.UniversityMapPointSerializer,
        pagination_class=None,
        url_path="map",
    )
    def map_points(self, request) -> Response:
        """Возвращает все вузы с координатами в облегчённом формате карты."""
        queryset = (
            self.filter_queryset(self.get_queryset())
            .exclude(lat__isnull=True)
            .exclude(lon__isnull=True)
        )
        queryset = queryset.only("id", "lat", "lon")
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
