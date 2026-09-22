from django.contrib import admin

from sova.reports.models import ReportJob


@admin.register(ReportJob)
class ReportJobAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "report_type", "format", "status", "created_at", "finished_at")
    list_filter = ("status", "format", "report_type")
    readonly_fields = [field.name for field in ReportJob._meta.fields]
