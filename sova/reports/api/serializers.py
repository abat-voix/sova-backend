from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.models import Direction, Product, Program, Organization
from sova.reports.enum import ReportFormat, ReportJobStatus, ReportOrdering
from sova.reports.models import ReportJob
from sova.reports.spec import INTERACTION_COLUMN_KEYS, ReportSpec


class ReportSpecSerializer(serializers.Serializer):
    """
    Параметры отчёта по взаимодействиям с организациями.

    Период — даты создания взаимодействия. Статус, этапы, ответственный
    и состав — состояние на момент построения. Пустой список фильтра — без ограничения.
    """

    default_error_messages = {
        "period_order": _("Дата начала периода позже даты окончания."),
        "period_too_long": _("Период не может быть длиннее {days} дней."),
        "unknown_ids": _("Не найдены объекты: {ids}."),
    }

    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
    organizations = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    directions = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    programs = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    products = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    responsibles = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
        help_text="ID пользователей — действующих ответственных.",
    )
    ordering = serializers.ChoiceField(
        choices=ReportOrdering.choices, required=False, default=ReportOrdering.CREATED_AT_DESC
    )
    columns = serializers.ListField(
        child=serializers.ChoiceField(choices=INTERACTION_COLUMN_KEYS),
        required=False,
        allow_null=True,
        allow_empty=False,
        help_text="Отображаемые колонки; по умолчанию — все. Идентификаторы возвращаются всегда.",
    )

    list_models = {
        "organizations": Organization,
        "directions": Direction,
        "programs": Program,
        "products": Product,
        "responsibles": get_user_model(),
    }

    def validate(self, attrs):
        date_from, date_to = attrs.get("date_from"), attrs.get("date_to")
        if date_from and date_to:
            if date_from > date_to:
                self.fail_field("date_to", "period_order")
            if (date_to - date_from).days + 1 > settings.REPORTS_MAX_PERIOD_DAYS:
                self.fail_field("date_to", "period_too_long", days=settings.REPORTS_MAX_PERIOD_DAYS)

        limit = settings.REPORTS_MAX_FILTER_ITEMS
        for name, model in self.list_models.items():
            values = list(dict.fromkeys(attrs.get(name, [])))
            if len(values) > limit:
                raise serializers.ValidationError(
                    {name: [serializers.ErrorDetail(f"Не более {limit} значений.", code="max_length")]}
                )
            if values:
                found = set(model.objects.filter(pk__in=values).values_list("pk", flat=True))
                missing = [str(value) for value in values if value not in found]
                if missing:
                    self.fail_field(name, "unknown_ids", ids=", ".join(missing))
            attrs[name] = values
        return attrs

    def fail_field(self, field: str, key: str, **kwargs):
        message = self.error_messages[key].format(**kwargs)
        raise serializers.ValidationError({field: [serializers.ErrorDetail(message, code=key)]})

    def to_spec(self, report_format: str = ReportFormat.XLSX) -> ReportSpec:
        data = self.validated_data
        return ReportSpec(
            date_from=data.get("date_from"),
            date_to=data.get("date_to"),
            organizations=tuple(data["organizations"]),
            directions=tuple(data["directions"]),
            programs=tuple(data["programs"]),
            products=tuple(data["products"]),
            responsibles=tuple(data["responsibles"]),
            ordering=data["ordering"],
            columns=tuple(data.get("columns") or INTERACTION_COLUMN_KEYS),
            format=report_format,
        )


class ReportPreviewRequestSerializer(ReportSpecSerializer):
    """Параметры предпросмотра: спецификация отчёта и страница."""

    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(
        min_value=1, max_value=settings.REPORTS_PREVIEW_MAX_PAGE_SIZE, required=False, default=50
    )


class ReportExportRequestSerializer(ReportSpecSerializer):
    """Параметры выгрузки: спецификация отчёта и формат файла."""

    format = serializers.ChoiceField(choices=ReportFormat.choices)


class ReportSummaryRequestSerializer(ReportSpecSerializer):
    """Параметры сводки и язык готовых подписей графиков."""

    locale = serializers.ChoiceField(choices=("ru", "en"), required=False, default="ru")


class ColumnSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()


class ReportMetaSerializer(serializers.Serializer):
    """Метаданные выборки: когда и по каким правилам построен отчёт."""

    report_type = serializers.CharField()
    generated_at = serializers.DateTimeField()
    period_basis = serializers.CharField(help_text="Поле, по которому применяется период.")
    active_stage_status = serializers.CharField(help_text="Статус этапа, который считается актуальным.")
    state_note = serializers.CharField()
    filters = serializers.DictField(help_text="Нормализованные применённые параметры.")
    columns = ColumnSerializer(many=True)
    available_columns = ColumnSerializer(many=True)
    locale = serializers.ChoiceField(choices=("ru", "en"), required=False)


class ProcessStatusSerializer(serializers.Serializer):
    workflow_instance_id = serializers.UUIDField()
    workflow = serializers.CharField()
    status = serializers.CharField()
    label = serializers.CharField()


class ActiveStageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    context_type = serializers.CharField()


class ReportRowSerializer(serializers.Serializer):
    """Строка отчёта. Отображаемые поля присутствуют, только если выбраны в `columns`."""

    interaction_id = serializers.UUIDField()
    organization_id = serializers.UUIDField(allow_null=True)
    direction_id = serializers.UUIDField(allow_null=True)
    interaction_direction_id = serializers.UUIDField(allow_null=True)
    program_id = serializers.UUIDField(allow_null=True)
    interaction_program_id = serializers.UUIDField(allow_null=True)
    product_id = serializers.UUIDField(allow_null=True)
    interaction_product_id = serializers.UUIDField(allow_null=True)
    responsible_ids = serializers.ListField(
        child=serializers.IntegerField(), help_text="Действующие КАМы взаимодействия по алфавиту."
    )
    organization = serializers.CharField(required=False)
    direction = serializers.CharField(required=False)
    program = serializers.CharField(required=False)
    product = serializers.CharField(required=False)
    process_status = ProcessStatusSerializer(many=True, required=False)
    active_stages = ActiveStageSerializer(many=True, required=False)
    responsible = serializers.ListField(
        child=serializers.CharField(), required=False, help_text="Имена КАМов в порядке `responsible_ids`."
    )
    created_at = serializers.DateTimeField(required=False)
    updated_at = serializers.DateTimeField(required=False)
    contract_numbers = serializers.ListField(child=serializers.CharField(), required=False)
    contract_signed_at = serializers.ListField(child=serializers.DateField(), required=False)
    license_status = serializers.CharField(required=False)
    license_valid_until_year = serializers.IntegerField(required=False, allow_null=True)


class ReportPreviewSerializer(serializers.Serializer):
    count = serializers.IntegerField(help_text="Общее число строк.")
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = ReportRowSerializer(many=True)
    meta = ReportMetaSerializer()


class DistributionItemSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_null=True)
    status = serializers.CharField(required=False, allow_null=True)
    stage = serializers.CharField(required=False, allow_null=True)
    label = serializers.CharField()
    interactions = serializers.IntegerField(help_text="Число уникальных взаимодействий.")


class ReportMetricSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    display_value = serializers.CharField()


class ChartPointSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    value = serializers.IntegerField()
    display_value = serializers.CharField()


class ChartItemSerializer(ChartPointSerializer):
    key = serializers.CharField(allow_null=True)


class ReportChartSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.ChoiceField(choices=("line", "horizontal_bar"))
    title = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    value_label = serializers.CharField()
    empty_message = serializers.CharField()
    tone = serializers.CharField()
    points = ChartPointSerializer(many=True, required=False)
    items = ChartItemSerializer(many=True, required=False)


class ReportSummarySerializer(serializers.Serializer):
    interactions_count = serializers.IntegerField(help_text="Уникальные взаимодействия.")
    rows_count = serializers.IntegerField()
    programs_count = serializers.IntegerField()
    products_count = serializers.IntegerField()
    by_responsible = DistributionItemSerializer(many=True)
    by_organization = DistributionItemSerializer(many=True)
    by_process_status = DistributionItemSerializer(many=True)
    by_active_stage = DistributionItemSerializer(many=True)
    metrics = ReportMetricSerializer(many=True)
    charts = ReportChartSerializer(many=True)
    chart_meta = serializers.DictField()
    meta = ReportMetaSerializer()


class ReportJobSerializer(serializers.ModelSerializer):
    """Состояние задания на выгрузку."""

    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ReportJob
        fields = (
            "id",
            "report_type",
            "format",
            "status",
            "spec",
            "created_at",
            "started_at",
            "finished_at",
            "expires_at",
            "file_size",
            "rows_count",
            "error_code",
            "error_message",
            "download_url",
        )
        read_only_fields = fields

    def get_download_url(self, job: ReportJob) -> str | None:
        if job.status != ReportJobStatus.READY:
            return None
        request = self.context.get("request")
        url = reverse("reports:report-job-download", args=[job.pk])
        return request.build_absolute_uri(url) if request else url
