from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api.serializers import CatalogImportErrorSerializer
from sova.catalog.api.views.mixins import ImportResponseMixin
from sova.core.api.views import SovaReadOnlyViewSet
from sova.training.api import filters, serializers
from sova.training.models import Learner, LearnerPersonalData, TrainingApplicationLearner
from sova.training.services.enrollment import training_enrollment_service
from sova.training.services.learner_import import learner_import_service
from sova.training.services.personal_data_access import personal_data_access_service
from sova.training.services.visibility import visible_applications


class LearnerViewSet(ImportResponseMixin, SovaReadOnlyViewSet):
    """
    Обучающиеся. Приходят только из файла «Пользователи» (`import/`), вручную не создаются и не меняются.

    Email и телефон в ответах замаскированы; полные персональные данные (`personal-data/`) — только администратору
    платформы, каждая выдача пишется в журнал доступа.
    """

    read_serializer_class = serializers.LearnerSerializer
    serializer_class = serializers.LearnerSerializer
    filterset_class = filters.LearnerFilter
    search_fields = ("last_name", "first_name", "middle_name")
    ordering_fields = ("last_name", "created_at")
    policy_actions = {
        "list": Action.TRAINING_READ,
        "retrieve": Action.TRAINING_READ,
        "personal_data": Action.TRAINING_PERSONAL_DATA_READ,
        "import_file": Action.CATALOG_IMPORT,
    }

    def get_queryset(self):
        """Обучающиеся с участием в заявках видимых потоков и признаком зачисления."""
        participations = training_enrollment_service.with_enrollment(
            TrainingApplicationLearner.objects
            .filter(application__in=visible_applications(self.request.user))
            .select_related("application__stream")
        )
        return Learner.objects.prefetch_related(Prefetch("participations", queryset=participations))

    def get_serializer_class(self):
        if self.action == "retrieve":
            return serializers.LearnerDetailSerializer
        return super().get_serializer_class()

    @extend_schema(request=None, responses=serializers.LearnerPersonalDataSerializer)
    @action(
        methods=["GET"],
        detail=True,
        url_path="personal-data",
        serializer_class=serializers.LearnerPersonalDataSerializer,
    )
    def personal_data(self, request, pk=None) -> Response:
        """Полные персональные данные обучающегося; выдача пишется в журнал доступа."""
        learner = self.get_object()
        data = LearnerPersonalData.objects.filter(learner=learner).first() or LearnerPersonalData(learner=learner)
        personal_data_access_service.log_access(user=request.user, learner=learner, request=request)
        return Response(self.get_serializer(data).data)

    @extend_schema(
        request={"multipart/form-data": serializers.LearnerImportSerializer},
        responses={200: serializers.LearnerImportResultSerializer, 400: CatalogImportErrorSerializer},
    )
    @action(
        methods=["POST"],
        detail=False,
        url_path="import",
        parser_classes=(MultiPartParser,),
        serializer_class=serializers.LearnerImportSerializer,
    )
    def import_file(self, request) -> Response:
        """
        Загрузка файла «Пользователи». С `stream` — создаётся заявка на поток, обучающиеся становятся её участниками
        (кто уже есть в заявке потока — пропускается с предупреждением); без `stream` — только обучающиеся.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.import_response(
            run=lambda: learner_import_service.import_file(
                source=serializer.validated_data["file"],
                user=request.user,
                stream=serializer.validated_data.get("stream"),
            ),
            data=lambda result: serializers.LearnerImportResultSerializer(
                {
                    "created": result.created,
                    "updated": result.updated,
                    "application": result.application.pk if result.application else None,
                    "warnings": self.import_warnings(result.warnings),
                }
            ).data,
        )
