from django.db.models import Count, IntegerField, OuterRef, Prefetch, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.core.api.exceptions import ConflictError
from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.exceptions import NoActiveResponsibleError
from sova.interactions.models import (
    Interaction,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    Responsible,
)
from sova.interactions.services import responsible_service, visible_interactions


def _active_count(model: type) -> Coalesce:
    """
    Подзапрос: число активных записей состава взаимодействия.

    Подзапрос вместо Count() по трём join'ам — иначе строки перемножились бы
    (направления × программы × продукты) и список стал бы тяжёлым.
    """
    counts = (
        model.objects
        .filter(interaction=OuterRef("pk"), is_active=True)
        .order_by()
        .values("interaction")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return Coalesce(Subquery(counts, output_field=IntegerField()), 0)


class InteractionViewSet(SovaBaseViewSet):
    """
    Взаимодействия с вузами и B2C-клиентами. Доступны CRUD операции.

    Состав выборки зависит от роли запрашивающего: КАМ видит взаимодействия, где он
    действующий ответственный, руководитель — свои и КАМов, администратор платформы — все.
    Взаимодействия без действующего ответственного видны всем ролям.

    Ответственного менеджера назначают и снимают действиями
    `assign-responsible` / `unassign-responsible`: он хранится с историей,
    поэтому напрямую в теле взаимодействия не редактируется.
    """

    read_serializer_class = serializers.InteractionSerializer
    serializer_class = serializers.WriteInteractionSerializer
    queryset = Interaction.objects.all()
    ordering_fields = "__all__"
    search_fields = (
        "comment",
        "university__name",
        "university__short_name",
        "b2c_client__full_name",
    )
    filterset_class = filters.InteractionFilter

    def get_queryset(self) -> QuerySet:
        """Взаимодействия, видимые пользователю по его роли в СОВА."""
        return self._with_details(visible_interactions(self.request.user))

    def _with_details(self, queryset: QuerySet) -> QuerySet:
        """Дополняет выборку счётчиками состава и действующим ответственным."""
        return (
            queryset
            .select_related("university", "b2c_client")
            .prefetch_related(
                Prefetch(
                    "responsibles",
                    queryset=Responsible.objects.filter(
                        unassigned_at__isnull=True,
                    ).select_related("manager"),
                    to_attr="current_responsibles",
                ),
            )
            .annotate(
                directions_count=_active_count(InteractionDirection),
                programs_count=_active_count(InteractionProgram),
                products_count=_active_count(InteractionProduct),
            )
        )

    def perform_create(self, serializer: serializers.WriteInteractionSerializer) -> None:
        """Пересоздание инстанса через аннотированный queryset для read-ответа."""
        super().perform_create(serializer)
        # Выборка без роли: созданное взаимодействие нужно вернуть автору в любом случае
        serializer.instance = self._with_details(Interaction.objects.all()).get(pk=serializer.instance.pk)

    @extend_schema(
        request=serializers.AssignResponsibleSerializer,
        responses={
            200: serializers.ResponsibleSerializer,
            201: serializers.ResponsibleSerializer,
        },
    )
    @action(
        methods=["POST"],
        detail=True,
        url_path="assign-responsible",
        serializer_class=serializers.AssignResponsibleSerializer,
    )
    def assign_responsible(self, request, pk=None) -> Response:
        """
        Назначает ответственного менеджера.

        Действующий ответственный, если он есть, закрывается и остаётся в истории.
        Повторное назначение того же менеджера ничего не меняет и возвращает 200.
        """
        interaction = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        responsible, created = responsible_service.assign(
            interaction=interaction,
            manager=serializer.validated_data["manager"],
            assigned_by=request.user,
        )

        return Response(
            data=serializers.ResponsibleSerializer(
                responsible,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        request=None,
        responses={200: serializers.ResponsibleSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        url_path="unassign-responsible",
    )
    def unassign_responsible(self, request, pk=None) -> Response:
        """Снимает действующего ответственного; запись остаётся в истории."""
        interaction = self.get_object()

        try:
            responsible = responsible_service.unassign(interaction=interaction)
        except NoActiveResponsibleError:
            raise ConflictError(
                detail=_("У взаимодействия нет действующего ответственного."),
                code="no_active_responsible",
            )

        return Response(
            data=serializers.ResponsibleSerializer(
                responsible,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
