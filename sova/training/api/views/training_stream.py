from django.db.models import Count, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.core.api.views import ReadWriteUpdateModelMixin, SovaReadOnlyViewSet
from sova.training.api import filters, serializers
from sova.training.enum import TrainingApplicationStatus
from sova.training.models import TrainingInstructor
from sova.training.services.stream import training_stream_service
from sova.training.services.visibility import visible_streams

# UUID в пути вложенного ресурса: невалидный id — 404 от роутера, а не ошибка запроса к БД
UUID_PATTERN = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"


class TrainingStreamViewSet(ReadWriteUpdateModelMixin, mixins.DestroyModelMixin, SovaReadOnlyViewSet):
    """
    Потоки обучения. Создаются возможностью `training.create` у действия процесса, здесь — просмотр, изменение
    и назначение преподавателей. Видны вместе со взаимодействием программы (раздел `training` политики).
    """

    read_serializer_class = serializers.TrainingStreamSerializer
    serializer_class = serializers.WriteTrainingStreamSerializer
    filterset_class = filters.TrainingStreamFilter
    search_fields = ("name", "interaction_program__program__name")
    ordering_fields = ("created_at", "starts_at", "name", "status")
    policy_actions = {
        "list": Action.TRAINING_READ,
        "retrieve": Action.TRAINING_READ,
        "update": Action.TRAINING_UPDATE,
        "partial_update": Action.TRAINING_UPDATE,
        "destroy": Action.TRAINING_UPDATE,
        "assign_instructor": Action.TRAINING_UPDATE,
        "unassign_instructor": Action.TRAINING_UPDATE,
    }

    def get_queryset(self):
        """Видимые потоки с программой, преподавателями, числом заявок, участников и оплативших."""
        return (
            visible_streams(self.request.user)
            .select_related(
                "interaction_program__program",
                "interaction_program__interaction__organization",
                "interaction_program__interaction__b2c_client",
            )
            .prefetch_related("instructors")
            .annotate(
                applications_count=Count("applications", distinct=True),
                # Участники и оплатившие — только в действующих заявках
                participants_count=Count(
                    "applications__participants",
                    filter=Q(applications__status=TrainingApplicationStatus.NEW),
                    distinct=True,
                ),
                paid_count=Count(
                    "applications__participants",
                    filter=Q(
                        applications__status=TrainingApplicationStatus.NEW,
                        applications__participants__is_paid=True,
                    ),
                    distinct=True,
                ),
            )
        )

    @extend_schema(
        request=serializers.AssignTrainingInstructorSerializer,
        responses=serializers.TrainingStreamSerializer,
    )
    @action(
        methods=["POST"],
        detail=True,
        url_path="instructors",
        serializer_class=serializers.AssignTrainingInstructorSerializer,
    )
    def assign_instructor(self, request, pk=None) -> Response:
        """Назначает преподавателя организации-контрагента на поток."""
        stream = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        training_stream_service.assign_instructor(
            stream=stream,
            instructor=serializer.validated_data["instructor"],
            user=request.user,
        )
        return Response(self.get_response_serializer(self.get_object()).data)

    @extend_schema(parameters=[OpenApiParameter("instructor_id", OpenApiTypes.UUID, OpenApiParameter.PATH)])
    @action(methods=["DELETE"], detail=True, url_path=rf"instructors/(?P<instructor_id>{UUID_PATTERN})")
    def unassign_instructor(self, request, pk=None, instructor_id=None) -> Response:
        """Снимает преподавателя с потока."""
        stream = self.get_object()
        instructor = TrainingInstructor.objects.filter(pk=instructor_id).first()
        if instructor is not None:
            training_stream_service.unassign_instructor(stream=stream, instructor=instructor)
        return Response(status=status.HTTP_204_NO_CONTENT)
