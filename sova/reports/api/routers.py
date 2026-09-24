from django.urls import path

from sova.reports.api import views

app_name = "reports"

urlpatterns = [
    path(
        "interactions/preview/",
        views.InteractionReportPreviewView.as_view(),
        name="interaction-report-preview",
    ),
    path(
        "interactions/summary/",
        views.InteractionReportSummaryView.as_view(),
        name="interaction-report-summary",
    ),
    path(
        "interactions/exports/",
        views.InteractionReportExportView.as_view(),
        name="interaction-report-export",
    ),
    path("exports/<uuid:pk>/", views.ReportJobDetailView.as_view(), name="report-job-detail"),
    path(
        "exports/<uuid:pk>/download/",
        views.ReportJobDownloadView.as_view(),
        name="report-job-download",
    ),
]
