from uuid import UUID

from django.db.models import Count, IntegerField, OuterRef, Prefetch, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.fields import UUIDField
from rest_framework.response import Response

from sova.core.api.exceptions import ConflictError
from sova.core.api.views import SovaBaseViewSet
from sova.catalog.models import ContactPerson
from sova.interactions.api import filters, serializers
from sova.interactions.exceptions import NoActiveResponsibleError
from sova.interactions.models import (
    Interaction,
    InteractionContact,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
    Responsible,
)
from sova.interactions.services import contact_link_service, responsible_service, visible_interactions


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

    @extend_schema(
        methods=["GET"],
        request=None,
        responses={200: serializers.InteractionContactSerializer(many=True)},
    )
    @extend_schema(
        methods=["POST"],
        request=serializers.LinkContactPersonSerializer,
        responses={200: serializers.InteractionContactSerializer},
    )
    @action(
        methods=["GET", "POST"],
        detail=True,
        url_path="contacts",
        pagination_class=None,
        filter_backends=[],
    )
    def contacts(self, request, pk=None) -> Response:
        """Возвращает активные контакты взаимодействия или добавляет новый контакт."""
        interaction = self.get_object()
        if request.method == "GET":
            links = (
                InteractionContact.objects.filter(
                    interaction=interaction,
                    unlinked_at__isnull=True,
                )
                .select_related("contact_person")
                .order_by("linked_at")
            )
            return Response(
                serializers.InteractionContactSerializer(
                    links,
                    many=True,
                    context=self.get_serializer_context(),
                ).data,
            )

        request_serializer = serializers.LinkContactPersonSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        try:
            contact = ContactPerson.objects.get(
                pk=request_serializer.validated_data["contact_person"],
            )
        except ContactPerson.DoesNotExist as error:
            raise NotFound(
                detail="Контактное лицо не найдено.",
                code="contact_not_found",
            ) from error

        link, _ = contact_link_service.link(
            interaction=interaction,
            contact_person=contact,
            actor=request.user,
        )
        link = InteractionContact.objects.select_related("contact_person").get(pk=link.pk)
        return Response(
            serializers.InteractionContactSerializer(
                link,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        request=None,
        parameters=[
            OpenApiParameter(
                name="contact_id",
                type=UUID,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={204: None},
    )
    @action(
        methods=["DELETE"],
        detail=True,
        url_path=r"contacts/(?P<contact_id>[^/.]+)",
        url_name="unlink-contact",
    )
    def unlink_contact(self, request, pk=None, contact_id=None) -> Response:
        """Закрывает активную привязку, сохраняя контакт и историю в каталоге."""
        interaction = self.get_object()
        try:
            parsed_contact_id = UUIDField().run_validation(contact_id)
        except ValidationError:
            raise ValidationError(
                detail="Некорректный UUID контактного лица.",
                code="invalid_contact_id",
            )
        try:
            contact = ContactPerson.objects.get(pk=parsed_contact_id)
        except ContactPerson.DoesNotExist as error:
            raise NotFound(
                detail="Контактное лицо не найдено.",
                code="contact_not_found",
            ) from error

        contact_link_service.unlink(
            interaction=interaction,
            contact_person=contact,
            actor=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
