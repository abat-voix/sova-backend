from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api import serializers as catalog_serializers
from sova.catalog.api.serializers import CatalogImportErrorSerializer
from sova.catalog.api.views.mixins import ImportResponseMixin
from sova.catalog.enum import CatalogType
from sova.catalog.exceptions import CatalogImportError, CatalogImportMappingError
from sova.catalog.services import catalog_import_mapping_service, import_file_service
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
    Обучающиеся: из файла «Пользователи» (`import/`, заголовки файла — `import/headers/`, маппинг колонок —
    `import/mapping/`) и вручную — КАМ, руководитель, администратор платформы.

    Удаления нет — карточку выключают (`is_active`). Email и телефон в списках замаскированы; полные персональные
    данные — `personal-data/`, каждый просмотр и каждое изменение пишутся в журнал доступа.
    """

    # PUT — только для `import/mapping/`: у `update` нет кода в `policy_actions`, политика его запрещает
    http_method_names = ("get", "post", "put", "patch", "head", "options")
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
        "import_file": Action.TRAINING_IMPORT,
        "import_headers": Action.TRAINING_IMPORT,
        # Маппинг файла «Пользователи» правят все, кто его загружает; маппинги справочников — `catalog.mappings.manage`
        "import_mapping": Action.TRAINING_IMPORT,
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

    @extend_schema(
        request={"multipart/form-data": catalog_serializers.CatalogImportHeadersSerializer},
        responses={200: catalog_serializers.CatalogImportHeadersResultSerializer, 400: CatalogImportErrorSerializer},
    )
    @action(
        methods=["POST"],
        detail=False,
        url_path="import/headers",
        url_name="import-headers",
        parser_classes=(MultiPartParser,),
        serializer_class=catalog_serializers.CatalogImportHeadersSerializer,
    )
    def import_headers(self, request) -> Response:
        """Заголовки файла «Пользователи» для настройки маппинга; ничего не импортирует."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            headers = import_file_service.read_headers(source=serializer.validated_data["file"])
        except CatalogImportError as error:
            return Response(
                data=CatalogImportErrorSerializer({"detail": str(error), "code": "import_error"}).data,
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(data=catalog_serializers.CatalogImportHeadersResultSerializer({"headers": headers}).data)

    @extend_schema(
        methods=["GET"],
        request=None,
        responses={200: catalog_serializers.CatalogImportTypeMappingFieldSerializer(many=True)},
    )
    @extend_schema(
        methods=["PUT"],
        request=catalog_serializers.WriteCatalogImportTypeMappingSerializer,
        responses={200: catalog_serializers.CatalogImportTypeMappingFieldSerializer(many=True)},
    )
    @action(
        methods=["GET", "PUT"],
        detail=False,
        url_path="import/mapping",
        url_name="import-mapping",
        serializer_class=catalog_serializers.WriteCatalogImportTypeMappingSerializer,
        filter_backends=(),
        pagination_class=None,
    )
    def import_mapping(self, request) -> Response:
        """
        Маппинг колонок файла «Пользователи» (тип `learner`) целиком, как `/api/catalog/import-mappings/by-type/learner/`.

        PUT заменяет маппинг атомарно; ошибки — в `mappings` по каноническим ключам.
        """
        if request.method == "GET":
            fields = catalog_import_mapping_service.get_for_type(catalog_type=CatalogType.LEARNER)
        else:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            try:
                fields = catalog_import_mapping_service.replace_for_type(
                    catalog_type=CatalogType.LEARNER,
                    mappings=serializer.validated_data["mappings"],
                )
            except CatalogImportMappingError as error:
                errors = {target_field: [message] for target_field, message in error.errors.items()}
                raise drf_serializers.ValidationError({"mappings": errors}) from error
        return Response(data=catalog_serializers.CatalogImportTypeMappingFieldSerializer(fields, many=True).data)
