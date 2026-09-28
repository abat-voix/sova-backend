from accounts.policy import Action
from sova.core.api.views import SovaBaseViewSet
from sova.training.api import filters, serializers
from sova.training.models import TrainingInstructor


class TrainingInstructorViewSet(SovaBaseViewSet):
    """Преподаватели организаций и B2C-клиентов — справочник, права как у каталога."""

    read_serializer_class = serializers.TrainingInstructorSerializer
    serializer_class = serializers.WriteTrainingInstructorSerializer
    queryset = TrainingInstructor.objects.select_related("organization", "b2c_client").prefetch_related(
        "directions",
        "programs",
    )
    filterset_class = filters.TrainingInstructorFilter
    search_fields = ("last_name", "first_name", "middle_name", "email", "lms_external_id")
    ordering_fields = ("last_name", "created_at")
    policy_actions = {
        "list": Action.CATALOG_READ,
        "retrieve": Action.CATALOG_READ,
        "create": Action.CATALOG_CREATE,
        "update": Action.CATALOG_UPDATE,
        "partial_update": Action.CATALOG_UPDATE,
        "destroy": Action.CATALOG_DELETE,
    }
