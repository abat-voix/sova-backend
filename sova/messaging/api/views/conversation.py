from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from accounts.policy import Action
from sova.core.api.exceptions import ConflictError
from sova.core.api.pagination import StandardPagination
from sova.messaging.api import serializers
from sova.messaging.exceptions import SystemConversationIsReadOnlyError
from sova.messaging.models import Conversation, ConversationParticipant
from sova.messaging.services import conversation_service, message_service
from sova.messaging.services.message_attachment import AttachmentNotFoundError, DuplicateAttachmentError


class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, GenericViewSet):
    """
    Беседы текущего пользователя: личные и системная.

    Выборка ограничена беседами, где пользователь участник — get_object() на
    чужой беседе возвращает 404, отдельная проверка прав не нужна. Создание
    личной беседы и обмен сообщениями — через действия ниже, а не через
    create/update: беседа как таковая пользователем не редактируется.
    """

    serializer_class = serializers.ConversationSerializer
    pagination_class = None
    policy_action = Action.MESSAGING_USE

    def get_queryset(self) -> QuerySet:
        """Беседы пользователя с предзагруженными участниками (для other_participant)."""
        if getattr(self, "swagger_fake_view", False):
            return Conversation.objects.none()
        return Conversation.objects.filter(participants__user=self.request.user).prefetch_related(
            Prefetch(
                "participants",
                queryset=ConversationParticipant.objects.select_related("user"),
            ),
        )

    @extend_schema(
        request=serializers.CreateDirectConversationSerializer,
        responses={200: serializers.ConversationSerializer},
    )
    @action(methods=["POST"], detail=False, url_path="direct")
    def direct(self, request) -> Response:
        """Возвращает личную беседу с указанным пользователем, создавая её при первом обращении."""
        serializer = serializers.CreateDirectConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        other_user = serializer.validated_data["user"]
        if other_user.pk == request.user.pk:
            raise ValidationError({"user": _("Нельзя открыть личную беседу с самим собой.")})

        conversation = conversation_service.get_or_create_direct(request.user, other_user)
        conversation = self.get_queryset().get(pk=conversation.pk)
        return Response(
            data=self.get_serializer(conversation).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        methods=["GET"],
        request=None,
        responses={200: serializers.ConversationRecipientSerializer(many=True)},
    )
    @action(
        methods=["GET"],
        detail=False,
        url_path="recipients",
        pagination_class=StandardPagination,
    )
    def recipients(self, request) -> Response:
        """Активные пользователи, которых текущий пользователь может выбрать для беседы."""
        queryset = get_user_model().objects.filter(is_active=True).exclude(pk=request.user.pk)
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(username__icontains=search)
            )
        queryset = queryset.order_by("last_name", "first_name", "pk")
        page = self.paginate_queryset(queryset)
        serializer = serializers.ConversationRecipientSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        methods=["GET"],
        request=None,
        responses={200: serializers.MessageSerializer(many=True)},
    )
    @extend_schema(
        methods=["POST"],
        request=serializers.SendMessageSerializer,
        responses={201: serializers.MessageSerializer},
    )
    @action(methods=["GET", "POST"], detail=True, url_path="messages", pagination_class=StandardPagination)
    def messages(self, request, pk=None) -> Response:
        """Возвращает историю сообщений беседы или отправляет новое."""
        conversation = self.get_object()

        if request.method == "GET":
            queryset = conversation.messages.select_related("sender").prefetch_related("attachments").order_by("-created_at")
            page = self.paginate_queryset(queryset)
            serializer = serializers.MessageSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = serializers.SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            message = message_service.send(
                conversation=conversation,
                sender=request.user,
                text=serializer.validated_data["text"],
                link=serializer.validated_data["link"],
                attachment_ids=serializer.validated_data["attachment_ids"],
            )
        except SystemConversationIsReadOnlyError:
            raise ConflictError(
                detail=_("В системную беседу нельзя писать."),
                code="system_conversation_read_only",
            )
        except DuplicateAttachmentError as exc:
            raise ValidationError({"attachment_ids": ["Идентификаторы вложений не должны повторяться."]}, code="duplicate_attachment_ids") from exc
        except AttachmentNotFoundError as exc:
            # Одинаковый ответ для отсутствующего, чужого и уже использованного файла.
            raise NotFound(detail="Вложение не найдено.", code="attachment_not_found") from exc

        return Response(
            data=serializers.MessageSerializer(message).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses={204: None})
    @action(methods=["POST"], detail=True, url_path="read")
    def read(self, request, pk=None) -> Response:
        """Отмечает беседу прочитанной текущим пользователем по текущий момент."""
        conversation = self.get_object()
        message_service.mark_read(conversation=conversation, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={200: {"type": "object", "properties": {"unread_count": {"type": "integer"}}}})
    @action(methods=["GET"], detail=False, url_path="unread-count")
    def unread_count(self, request) -> Response:
        """Суммарное число непрочитанных сообщений пользователя по всем беседам."""
        return Response(data={"unread_count": message_service.unread_count(request.user)})
