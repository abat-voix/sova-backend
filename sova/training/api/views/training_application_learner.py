from rest_framework import mixins

from accounts.policy import Action
from sova.core.api.views import ReadWriteCreateModelMixin, ReadWriteUpdateModelMixin, SovaReadOnlyViewSet
from sova.training.api import filters, serializers
from sova.training.services.application import training_application_service
from sova.training.services.enrollment import training_enrollment_service
from sova.training.services.visibility import visible_application_learners


class TrainingApplicationLearnerViewSet(
    ReadWriteCreateModelMixin,
    ReadWriteUpdateModelMixin,
    mixins.DestroyModelMixin,
    SovaReadOnlyViewSet,
):
    """
    Участники заявок. Добавляются загрузкой «Пользователей» с потоком или вручную — например, чтобы отметить
    оплату без загрузки JSON. Изменяется только факт оплаты `is_paid`; оплатившего участника не удаляют.
    """

    read_serializer_class = serializers.TrainingApplicationLearnerSerializer
    serializer_class = serializers.WriteTrainingApplicationLearnerSerializer
    filterset_class = filters.TrainingApplicationLearnerFilter
    search_fields = ("learner__last_name", "learner__first_name")
    ordering_fields = ("created_at",)
    policy_actions = {
        "list": Action.TRAINING_READ,
        "retrieve": Action.TRAINING_READ,
        "create": Action.TRAINING_UPDATE,
        "update": Action.TRAINING_UPDATE,
        "partial_update": Action.TRAINING_UPDATE,
        "destroy": Action.TRAINING_UPDATE,
    }

    def get_queryset(self):
        """Участники заявок видимых потоков с признаком зачисления."""
        return training_enrollment_service.with_enrollment(
            visible_application_learners(self.request.user).select_related("learner")
        )

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return serializers.UpdateTrainingApplicationLearnerSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        if "new_learner" in data:
            serializer.instance = training_application_service.add_new_learner(
                application=data["application"],
                learner_fields=data["new_learner"],
                is_paid=data.get("is_paid", False),
            )
            return
        serializer.instance = training_application_service.add_learner(
            application=data["application"],
            learner=data["learner"],
            is_paid=data.get("is_paid", False),
        )

    def perform_update(self, serializer) -> None:
        training_application_service.set_paid(
            participant=serializer.instance,
            is_paid=serializer.validated_data.get("is_paid", serializer.instance.is_paid),
        )

    def perform_destroy(self, instance) -> None:
        training_application_service.delete_participant(instance)

    def get_response_serializer(self, instance, **kwargs):
        # Ответ на запись — с признаком зачисления, как при чтении
        return super().get_response_serializer(self.get_queryset().get(pk=instance.pk), **kwargs)
