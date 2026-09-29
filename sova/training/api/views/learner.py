from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api.serializers import CatalogImportErrorSerializer
from sova.catalog.api.views.mixins import ImportResponseMixin
from sova.core.api.views import SovaBaseViewSet
from sova.training.api import filters, serializers
from sova.training.models import Learner, LearnerPersonalData, TrainingApplicationLearner
from sova.training.services.enrollment import training_enrollment_service
from sova.training.services.learner import learner_service
from sova.training.services.learner_import import learner_import_service
from sova.training.services.personal_data_access import personal_data_access_service
from sova.training.services.visibility import visible_applications


class LearnerViewSet(ImportResponseMixin, SovaBaseViewSet):
    """
    Обучающиеся: из файла «Пользователи» (`import/`) и вручную — КАМ, руководитель, администратор платформы.

    Удаления нет — карточку выключают (`is_active`). Email и телефон в списках замаскированы; полные персональные
    данные — `personal-data/`, каждый просмотр и каждое изменение пишутся в журнал доступа.
    """

    http_method_names = ("get", "post", "patch", "head", "options")
    read_serializer_class = serializers.LearnerSerializer
    serializer_class = serializers.WriteLearnerSerializer
    filterset_class = filters.LearnerFilter
    search_fields = ("last_name", "first_name", "middle_name")
    ordering_fields = ("last_name", "created_at")
    policy_actions = {
        "list": Action.TRAINING_READ,
        "retrieve": Action.TRAINING_READ,
        "create": Action.TRAINING_UPDATE,
        "partial_update": Action.TRAINING_UPDATE,
        "personal_data": {
            "GET": Action.TRAINING_PERSONAL_DATA_READ,
            "PATCH": Action.TRAINING_PERSONAL_DATA_UPDATE,
        },
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

    def perform_create(self, serializer) -> None:
        serializer.instance = learner_service.create(**serializer.validated_data)

    def perform_update(self, serializer) -> None:
        serializer.instance = learner_service.update(serializer.instance, **serializer.validated_data)

    @extend_schema(methods=["GET"], request=None, responses=serializers.LearnerPersonalDataSerializer)
    @extend_schema(
        methods=["PATCH"],
        request=serializers.WriteLearnerPersonalDataSerializer,
        responses=serializers.LearnerPersonalDataSerializer,
    )
    @action(
        methods=["GET", "PATCH"],
        detail=True,
        url_path="personal-data",
        serializer_class=serializers.LearnerPersonalDataSerializer,
    )
    def personal_data(self, request, pk=None) -> Response:
        """Полные персональные данные: просмотр и правка; каждый просмотр и изменение пишутся в журнал доступа."""
        learner = self.get_object()
        if request.method == "PATCH":
            serializer = serializers.WriteLearnerPersonalDataSerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            data = learner_service.update_personal_data(
                learner=learner, data=serializer.validated_data, user=request.user, request=request
            )
            # В ответе — все ПД, а не только изменённые поля: их выдача — такой же просмотр
            personal_data_access_service.log_access(user=request.user, learner=learner, request=request)
            return Response(self.get_serializer(data).data)
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
