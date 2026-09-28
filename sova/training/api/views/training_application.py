from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.core.api.views import ReadWriteCreateModelMixin, ReadWriteUpdateModelMixin, SovaReadOnlyViewSet
from sova.training.api import filters, serializers
from sova.training.models import TrainingApplicationLearner
from sova.training.services.application import training_application_service
from sova.training.services.enrollment import training_enrollment_service
from sova.training.services.visibility import visible_applications


class TrainingApplicationViewSet(
    ReadWriteCreateModelMixin,
    ReadWriteUpdateModelMixin,
    mixins.DestroyModelMixin,
    SovaReadOnlyViewSet,
):
    """
    Заявки на потоки. Создаются вручную по видимому потоку или загрузкой файла «Пользователи» с выбранным потоком.

    Поток после создания не меняется. `cancel` отменяет заявку — её участники перестают считаться зачисленными;
    заявку с оплатившими участниками не удаляют.
    """

    read_serializer_class = serializers.TrainingApplicationSerializer
    serializer_class = serializers.WriteTrainingApplicationSerializer
    filterset_class = filters.TrainingApplicationFilter
    search_fields = ("participants__learner__last_name", "comment")
    ordering_fields = ("created_at", "status")
    policy_actions = {
        "list": Action.TRAINING_READ,
        "retrieve": Action.TRAINING_READ,
        "create": Action.TRAINING_UPDATE,
        "update": Action.TRAINING_UPDATE,
        "partial_update": Action.TRAINING_UPDATE,
        "destroy": Action.TRAINING_UPDATE,
        "cancel": Action.TRAINING_UPDATE,
    }

    def get_queryset(self):
        """Видимые заявки с участниками и признаком зачисления."""
        participants = training_enrollment_service.with_enrollment(
            TrainingApplicationLearner.objects.select_related("learner")
        )
        return (
            visible_applications(self.request.user)
            .select_related("stream")
            .prefetch_related(Prefetch("participants", queryset=participants))
        )

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return serializers.UpdateTrainingApplicationSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer) -> None:
        serializer.instance = training_application_service.create_application(
            stream=serializer.validated_data["stream"],
            comment=serializer.validated_data.get("comment", ""),
            user=self.request.user,
        )

    def perform_destroy(self, instance) -> None:
        training_application_service.delete_application(instance)

    def get_response_serializer(self, instance, **kwargs):
        # Ответ на запись — с участниками и зачислением, как при чтении
        return super().get_response_serializer(self.get_queryset().get(pk=instance.pk), **kwargs)

    @extend_schema(request=None, responses=serializers.TrainingApplicationSerializer)
    @action(methods=["POST"], detail=True)
    def cancel(self, request, pk=None) -> Response:
        """Отменяет заявку: её участники перестают считаться зачисленными."""
        application = training_application_service.cancel(self.get_object())
        return Response(self.get_response_serializer(application).data)
