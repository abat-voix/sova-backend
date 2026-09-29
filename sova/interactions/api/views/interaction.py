from uuid import UUID

from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Prefetch, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.fields import UUIDField
from rest_framework.response import Response

from accounts.exceptions import KamHasHeadError
from accounts.models import SystemRole
from accounts.policy import Action
from accounts.services import get_system_role
from sova.core.api.exceptions import ConflictError
from sova.core.api.views import SovaBaseViewSet
from sova.catalog.models import ContactPerson
from sova.catalog.services.contact_affiliation import contact_affiliation_service
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
from sova.interactions.services import (
    assignment_candidates,
    contact_link_service,
    interaction_service,
    responsible_service,
    visible_interactions,
)
from sova.messaging.api.serializers import ConversationSerializer
from sova.messaging.models import Conversation, ConversationParticipant
from sova.messaging.services import conversation_service


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
    Взаимодействия с организациями и B2C-клиентами. Доступны CRUD операции.

    Состав выборки зависит от роли запрашивающего: КАМ видит взаимодействия, где он
    действующий ответственный, руководитель — свои, КАМов своей команды и КАМов без руководителя, администратор
    платформы — все.
    Взаимодействия без действующего ответственного видны всем ролям.
    КАМ, создавший взаимодействие, сразу становится его ответственным.

    Ответственного менеджера назначают и снимают действиями
    `assign-responsible` / `unassign-responsible`: он хранится с историей,
    поэтому напрямую в теле взаимодействия не редактируется.

    Права на операции — `policy_actions` (`accounts.policy`): наблюдатель только читает взаимодействия и их контакты.

    Удалить можно только незапущенное взаимодействие — без процесса и договоров (`can_delete`); иначе 409.
    """

    policy_actions = {
        "list": Action.INTERACTIONS_READ,
        "retrieve": Action.INTERACTIONS_READ,
        "create": Action.INTERACTIONS_CREATE,
        "update": Action.INTERACTIONS_UPDATE,
        "partial_update": Action.INTERACTIONS_UPDATE,
        "destroy": Action.INTERACTIONS_DELETE,
        "assignable_managers": Action.INTERACTIONS_RESPONSIBLES_ASSIGN,
        "assign_responsible": Action.INTERACTIONS_RESPONSIBLES_ASSIGN,
        "unassign_responsible": Action.INTERACTIONS_RESPONSIBLES_UNASSIGN,
        "contacts": {"GET": Action.INTERACTIONS_READ, "POST": Action.INTERACTIONS_UPDATE},
        "unlink_contact": Action.INTERACTIONS_UPDATE,
        "chat": Action.INTERACTIONS_CHAT,
        "chat_participants": Action.INTERACTIONS_CHAT,
    }

    read_serializer_class = serializers.InteractionSerializer
    serializer_class = serializers.WriteInteractionSerializer
    queryset = Interaction.objects.all()
    ordering_fields = "__all__"
    search_fields = (
        "comment",
        "organization__name",
        "organization__short_name",
        "b2c_client__full_name",
    )
    filterset_class = filters.InteractionFilter

    def get_queryset(self) -> QuerySet:
        """Взаимодействия, видимые пользователю по его роли в СОВА."""
        return self._with_details(visible_interactions(self.request.user))

    def _with_details(self, queryset: QuerySet) -> QuerySet:
        """Дополняет выборку счётчиками состава, действующим ответственным и признаком `can_delete`."""
        return (
            interaction_service.annotate_can_delete(queryset)
            .select_related("organization", "b2c_client")
            .prefetch_related(
                Prefetch(
                    "responsibles",
                    queryset=Responsible.objects.filter(
                        unassigned_at__isnull=True,
                    ).select_related("manager").order_by("assigned_at", "pk"),
                    to_attr="current_responsibles",
                ),
            )
            .annotate(
                directions_count=_active_count(InteractionDirection),
                programs_count=_active_count(InteractionProgram),
                products_count=_active_count(InteractionProduct),
            )
        )

    def perform_destroy(self, instance: Interaction) -> None:
        """Удаляет незапущенное взаимодействие; запущенное или с договорами — 409."""
        interaction_service.delete(instance)

    def perform_create(self, serializer: serializers.WriteInteractionSerializer) -> None:
        """Создаёт взаимодействие; КАМ-автор сразу становится ответственным. Ответ — из аннотированного queryset."""
        with transaction.atomic():
            super().perform_create(serializer)
            if get_system_role(self.request.user) == SystemRole.KAM:
                responsible_service.assign(
                    interaction=serializer.instance,
                    manager=self.request.user,
                    assigned_by=self.request.user,
                )
        # Выборка без роли: созданное взаимодействие нужно вернуть автору в любом случае
        serializer.instance = self._with_details(Interaction.objects.all()).get(pk=serializer.instance.pk)

    @extend_schema(request=None, responses={200: serializers.ManagerCandidateSerializer(many=True)})
    @action(methods=["GET"], detail=True, url_path="assignable-managers")
    def assignable_managers(self, request, pk=None) -> Response:
        """
        Кандидаты для окна назначения ответственного: кого пользователь может назначить и КАМы из реестра.

        Руководителю и администратору КАМы из реестра договоров взаимодействия идут первыми с `from_registry=true`;
        тот, кого пользователь назначить не вправе (например, КАМ чужой команды), показывается с `assignable=false`.
        КАМ получает только себя, без подсказки реестра. Назначение — `assign-responsible`.
        """
        candidates = assignment_candidates(interaction=self.get_object(), actor=request.user)
        return Response(
            data=serializers.ManagerCandidateSerializer(candidates, many=True, context=self.get_serializer_context()).data,
        )

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
        Добавляет ответственного менеджера.

        Действующие ответственные остаются: у взаимодействия может быть несколько КАМов.
        Администратор назначает активных КАМов и руководителей, руководитель — себя, КАМов своей команды и свободных
        (свободный вступает в его команду), КАМ — только себя.
        Повторное назначение того же менеджера ничего не меняет и возвращает 200.
        """
        interaction = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            responsible, created = responsible_service.assign_by(
                interaction=interaction,
                manager=serializer.validated_data["manager"],
                actor=request.user,
            )
        except KamHasHeadError:
            raise ConflictError(detail=_("У КАМа уже есть другой руководитель."), code="kam_has_head")

        return Response(
            data=serializers.ResponsibleSerializer(
                responsible,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        request=serializers.UnassignResponsibleSerializer,
        responses={200: serializers.ResponsibleSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        url_path="unassign-responsible",
        serializer_class=serializers.UnassignResponsibleSerializer,
    )
    def unassign_responsible(self, request, pk=None) -> Response:
        """
        Снимает указанного ответственного; запись остаётся в истории, остальные КАМы не меняются.

        Администратор снимает любого, руководитель — себя и КАМов своей команды, КАМ — никого (403).
        """
        interaction = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            responsible = responsible_service.unassign(
                interaction=interaction,
                manager=serializer.validated_data["manager"],
            )
        except NoActiveResponsibleError:
            raise ConflictError(
                detail=_("Менеджер не назначен ответственным за взаимодействие."),
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
            links = contact_affiliation_service.annotate_interaction_position(links)
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
        link = contact_affiliation_service.annotate_interaction_position(
            InteractionContact.objects.select_related("contact_person")
        ).get(pk=link.pk)
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

    def _chat_queryset(self) -> QuerySet:
        """Чаты Взаимодействий с предзагруженными участниками (для сериализации)."""
        return Conversation.objects.prefetch_related(
            Prefetch(
                "participants",
                queryset=ConversationParticipant.objects.select_related("user"),
            ),
        ).select_related("interaction__organization", "interaction__b2c_client")

    @extend_schema(
        methods=["GET"],
        request=None,
        responses={200: ConversationSerializer, 404: None},
    )
    @extend_schema(
        methods=["POST"],
        request=serializers.CreateInteractionChatSerializer,
        responses={200: ConversationSerializer, 201: ConversationSerializer},
    )
    @action(
        methods=["GET", "POST"],
        detail=True,
        url_path="chat",
        serializer_class=serializers.CreateInteractionChatSerializer,
    )
    def chat(self, request, pk=None) -> Response:
        """
        Чат Взаимодействия: получение и создание.

        GET отдаёт чат, только если он уже создан и запрашивающий — его участник;
        иначе — 404, в том числе если чат существует, но пользователь не приглашён.
        """
        interaction = self.get_object()

        if request.method == "GET":
            conversation = self._chat_queryset().filter(
                interaction=interaction,
                participants__user=request.user,
            ).first()
            if conversation is None:
                raise NotFound(detail="Чат Взаимодействия не найден.", code="chat_not_found")
            return Response(
                data=ConversationSerializer(conversation, context=self.get_serializer_context()).data,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation, created = conversation_service.get_or_create_interaction(
            interaction=interaction,
            actor=request.user,
            users=serializer.validated_data["participant_ids"],
        )
        if not created and not ConversationParticipant.objects.filter(
            conversation=conversation,
            user=request.user,
        ).exists():
            raise ConflictError(
                detail=_("Чат Взаимодействия уже создан, но вы не его участник."),
                code="chat_exists_not_participant",
            )

        conversation = self._chat_queryset().get(pk=conversation.pk)
        return Response(
            data=ConversationSerializer(conversation, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(
        request=serializers.AddChatParticipantsSerializer,
        responses={200: ConversationSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        url_path="chat/participants",
        serializer_class=serializers.AddChatParticipantsSerializer,
    )
    def chat_participants(self, request, pk=None) -> Response:
        """Добавляет участников в уже созданный чат Взаимодействия."""
        interaction = self.get_object()
        conversation = Conversation.objects.filter(interaction=interaction).first()
        if conversation is None:
            raise NotFound(detail="Чат Взаимодействия не найден.", code="chat_not_found")
        if not conversation_service.can_add_participants(conversation, request.user):
            raise PermissionDenied(detail=_("Недостаточно прав для изменения состава чата."))

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation_service.add_participants(conversation, serializer.validated_data["participant_ids"])

        conversation = self._chat_queryset().get(pk=conversation.pk)
        return Response(
            data=ConversationSerializer(conversation, context=self.get_serializer_context()).data,
        )
