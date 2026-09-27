from accounts.policy import Action
from sova.core.api.views import SovaBaseViewSet
from sova.training.api import filters, serializers
from sova.training.models import TrainingInstructorQualification


class TrainingInstructorQualificationViewSet(SovaBaseViewSet):
    """Подготовка преподавателей: обучение преподавателей и повышение квалификации."""

    read_serializer_class = serializers.TrainingInstructorQualificationSerializer
    serializer_class = serializers.TrainingInstructorQualificationSerializer
    queryset = TrainingInstructorQualification.objects.select_related("instructor", "program")
    filterset_class = filters.TrainingInstructorQualificationFilter
    ordering_fields = ("completed_at", "created_at")
    policy_actions = {
        "list": Action.CATALOG_READ,
        "retrieve": Action.CATALOG_READ,
        "create": Action.CATALOG_CREATE,
        "update": Action.CATALOG_UPDATE,
        "partial_update": Action.CATALOG_UPDATE,
        "destroy": Action.CATALOG_DELETE,
    }

    def perform_create(self, serializer) -> None:
        serializer.save(created_by=self.request.user)
