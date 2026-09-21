from django.db.models import Count, IntegerField, OuterRef, Prefetch, QuerySet, Subquery
from django.db.models.functions import Coalesce
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.core.api.views import SovaReadOnlyViewSet
from sova.interactions.services import visible_interactions
from sova.processes.api import filters, serializers
from sova.processes.api.errors import translate_engine_errors
from sova.processes.models import ActionAttachment, ActionInstance
from sova.processes.services import workflow_engine_service
from sova.workflows.models import ActionOutcome

_ORDERING_FIELDS = (
    "planned_start",
    "planned_end",
    "actual_start",
    "actual_end",
    "execution_no",
    "status",
)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                name="ordering",
                description=(
                    "Поле сортировки; префикс «-» — по убыванию. "
                    "Другие поля модели для сортировки не принимаются."
                ),
                enum=[
                    f"{prefix}{field}" for field in _ORDERING_FIELDS for prefix in ("", "-")
                ],
            ),
        ],
    ),
)
class ActionInstanceViewSet(SovaReadOnlyViewSet):
    """
    Экземпляры действий этапа: просмотр, завершение и откат.

    Создаёт и меняет экземпляры только движок: действия появляются при запуске процесса, запускаются
    по зависимостям и переходам, завершаются запросом `complete`, откатываются запросом `cancel`.

    Выборка ограничена взаимодействиями, доступными пользователю по роли в СОВА: КАМ видит действия
    своих взаимодействий, руководитель — свои и КАМов, администратор платформы — все. Внутри доступного
    охват выбирает параметр `scope`.
    """

    serializer_class = serializers.ActionInstanceSerializer
    queryset = ActionInstance.objects.all()
    ordering_fields = _ORDERING_FIELDS
    search_fields = ("action_name_snapshot", "status")
    filterset_class = filters.ActionInstanceFilter

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        """
        Применяет фильтры только к списку.

        У `scope` есть значение по умолчанию (`mine`), и без этой оговорки оно сужало бы и выборку
        detail-маршрутов: чужое действие нельзя было бы ни открыть, ни завершить, ни откатить.
        Границы доступного всё равно заданы в `get_queryset` и действуют всегда.
        """
        if self.action != "list":
            return queryset
        return super().filter_queryset(queryset)

    def get_queryset(self) -> QuerySet:
        """Действия доступных пользователю взаимодействий, со всем, что нужно карточке."""
        # Число вложений — подзапросом, иначе GROUP BY лёг бы на всю широкую строку карточки
        attachments = (
            ActionAttachment.objects
            .filter(action_instance=OuterRef("pk"))
            .order_by()
            .values("action_instance")
            .annotate(total=Count("pk"))
            .values("total")
        )
        return (
            super()
            .get_queryset()
            .filter(
                stage_instance__workflow_instance__interaction__in=visible_interactions(self.request.user),
            )
            .select_related(
                "action",
                "responsible",
                "result__created_by",
                "stage_instance__stage",
                "stage_instance__workflow_instance__interaction__university",
                "stage_instance__workflow_instance__interaction__b2c_client",
            )
            .prefetch_related(
                Prefetch(
                    "action__action_outcomes",
                    queryset=ActionOutcome.objects.filter(is_active=True).order_by("code"),
                    to_attr="active_outcomes",
                ),
            )
            .annotate(attachments_count=Coalesce(Subquery(attachments, output_field=IntegerField()), 0))
        )

    @extend_schema(
        request=serializers.CompleteActionSerializer,
        responses={200: serializers.CompleteActionResultSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.CompleteActionSerializer,
    )
    def complete(self, request, pk=None) -> Response:
        """
        Завершает действие с выбранным исходом и двигает процесс.

        Ответ описывает, что изменилось: результат, запущенные действия, открытые и закрытые этапы, завершён ли
        процесс. Ошибки: 409 (`invalid_state`) — действие не в работе; 400 — нарушены правила исхода
        (`outcome_mismatch`, `outcome_inactive`, `is_comment_required`, `is_attachment_required`).
        """
        action_instance = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with translate_engine_errors():
            outcome = workflow_engine_service.complete_action(
                action_instance=action_instance,
                outcome=serializer.validated_data["outcome"],
                comment=serializer.validated_data["comment"],
                completed_by=request.user,
            )

        return Response(
            data=serializers.CompleteActionResultSerializer(
                outcome,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        request=serializers.CancelActionSerializer,
        responses={200: serializers.CancelActionResultSerializer},
    )
    @action(
        methods=["POST"],
        detail=True,
        serializer_class=serializers.CancelActionSerializer,
    )
    def cancel(self, request, pk=None) -> Response:
        """
        Откатывает выполненное действие: новое исполнение вместо отменённого.

        Откатить можно только последнее исполнение, и только если от него не зависит уже выполненное действие
        того же этапа. Если действие закрыло свой этап, сначала откатывают сам этап. Ошибки: 409 (`invalid_state`)
        — действие не выполнено, не последнее исполнение или этап не в работе; 400 (`has_completed_dependent`) —
        от действия зависит уже выполненное действие.
        """
        action_instance = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with translate_engine_errors():
            outcome = workflow_engine_service.cancel_action(
                action_instance=action_instance,
                reason=serializer.validated_data["reason"],
                cancelled_by=request.user,
            )

        return Response(
            data=serializers.CancelActionResultSerializer(
                outcome,
                context=self.get_serializer_context(),
            ).data,
            status=status.HTTP_200_OK,
        )
