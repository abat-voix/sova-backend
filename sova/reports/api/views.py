from django.conf import settings
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, Throttled
from rest_framework.response import Response
from rest_framework.views import APIView

from sova.core.api.exceptions import ConflictError
from sova.reports.api import serializers
from sova.reports.enum import ReportJobStatus
from sova.reports.models import ReportJob
from sova.reports.services import jobs
from sova.reports.services.dataset import ReportDataset
from sova.reports.services.exporters import CONTENT_TYPES
from sova.reports.services.summary import build_summary

TAGS = ["reports"]


class Gone(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = _("Срок хранения файла истёк.")
    default_code = "expired"


class InteractionReportPreviewView(APIView):
    """
    Предпросмотр отчёта по взаимодействиям: страница строк, общее число строк и метаданные.

    Строка — продукт взаимодействия с программой и направлением; затем программы без продуктов
    и направления без программ; взаимодействие без состава — одна строка. В выборку попадают
    только взаимодействия, доступные пользователю по роли.
    """

    @extend_schema(
        tags=TAGS,
        request=serializers.ReportPreviewRequestSerializer,
        responses={200: serializers.ReportPreviewSerializer},
    )
    def post(self, request):
        serializer = serializers.ReportPreviewRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dataset = ReportDataset(user=request.user, spec=serializer.to_spec())
        page = serializer.validated_data["page"]
        page_size = serializer.validated_data["page_size"]
        start, stop = (page - 1) * page_size, page * page_size

        results, count = [], 0
        for row in dataset.iter_rows():
            if start <= count < stop:
                results.append(row.to_dict(dataset.columns))
            count += 1

        return Response(
            {
                "count": count,
                "page": page,
                "page_size": page_size,
                "results": results,
                "meta": dataset.metadata(),
            }
        )


class InteractionReportSummaryView(APIView):
    """
    Статистика отчёта: уникальные взаимодействия и распределения по ответственным, вузам,
    статусам процесса и актуальным этапам. Считается из той же выборки, что и предпросмотр.
    """

    @extend_schema(
        tags=TAGS,
        request=serializers.ReportSpecSerializer,
        responses={200: serializers.ReportSummarySerializer},
    )
    def post(self, request):
        serializer = serializers.ReportSpecSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dataset = ReportDataset(user=request.user, spec=serializer.to_spec())
        return Response({**build_summary(dataset.iter_rows()), "meta": dataset.metadata()})


class InteractionReportExportView(APIView):
    """
    Создаёт задание на выгрузку отчёта в XLSX, XLS, PDF или JSON и возвращает 202.

    Файл строится в фоне; состояние — `GET /api/reports/exports/{id}/`.
    """

    @extend_schema(
        tags=TAGS,
        request=serializers.ReportExportRequestSerializer,
        responses={202: serializers.ReportJobSerializer},
    )
    def post(self, request):
        serializer = serializers.ReportExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        active = ReportJob.objects.filter(
            owner=request.user, status__in=(ReportJobStatus.QUEUED, ReportJobStatus.RUNNING)
        ).count()
        if active >= settings.REPORTS_MAX_ACTIVE_JOBS_PER_USER:
            raise Throttled(detail=_("Слишком много незавершённых выгрузок. Дождитесь их окончания."))
        job = jobs.create_job(request.user, serializer.to_spec(serializer.validated_data["format"]))
        return Response(
            serializers.ReportJobSerializer(job, context={"request": request}).data,
            status=status.HTTP_202_ACCEPTED,
        )


def _own_job(request, pk) -> ReportJob:
    # Чужое задание неотличимо от несуществующего
    return get_object_or_404(ReportJob, pk=pk, owner=request.user)


class ReportJobDetailView(APIView):
    """Состояние задания на выгрузку. Доступно только владельцу."""

    @extend_schema(tags=TAGS, responses={200: serializers.ReportJobSerializer})
    def get(self, request, pk):
        job = _own_job(request, pk)
        return Response(serializers.ReportJobSerializer(job, context={"request": request}).data)


class ReportJobDownloadView(APIView):
    """Скачивание готового файла. 409 — файл ещё не готов, 410 — срок хранения истёк."""

    @extend_schema(
        tags=TAGS,
        responses={
            (200, "application/octet-stream"): OpenApiResponse(OpenApiTypes.BINARY),
            404: OpenApiResponse(description="Задание не найдено"),
            409: OpenApiResponse(description="Файл не готов"),
            410: OpenApiResponse(description="Срок хранения истёк"),
        },
    )
    def get(self, request, pk):
        job = _own_job(request, pk)
        if job.status != ReportJobStatus.READY or not job.file:
            raise ConflictError(detail=_("Файл отчёта ещё не готов."), code="not_ready")
        if job.expires_at and job.expires_at <= timezone.now():
            raise Gone()
        try:
            handle = job.file.open("rb")
        except FileNotFoundError:
            raise Gone(detail=_("Файл отчёта больше недоступен."), code="missing")
        filename = f"report-{timezone.localtime(job.finished_at):%Y%m%d-%H%M%S}.{job.format}"
        response = FileResponse(
            handle, as_attachment=True, filename=filename, content_type=CONTENT_TYPES[job.format]
        )
        response["Cache-Control"] = "private, no-store"
        return response
