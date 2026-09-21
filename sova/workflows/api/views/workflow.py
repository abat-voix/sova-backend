from django.db import transaction
from django.db.models import Count, QuerySet

from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.enum import WorkflowChangeType
from sova.workflows.models import Workflow
from sova.workflows.services import workflow_audit_service


class WorkflowViewSet(WorkflowAuditMixin, SovaBaseViewSet):
    """Шаблоны workflow. Доступны CRUD операции; правки пишутся в аудит."""

    read_serializer_class = serializers.WorkflowSerializer
    serializer_class = serializers.WriteWorkflowSerializer
    queryset = Workflow.objects.all()
    ordering_fields = "__all__"
    search_fields = ("name", "code", "description")
    filterset_class = filters.WorkflowFilter

    def get_queryset(self) -> QuerySet:
        """Queryset со счётчиком этапов."""
        return (
            super()
            .get_queryset()
            .select_related("created_by")
            .annotate(stages_count=Count("workflow_stages", distinct=True))
            .order_by("name")  # annotate() со GROUP BY сбрасывает Meta.ordering
        )

    @transaction.atomic
    def perform_create(self, serializer: serializers.WriteWorkflowSerializer) -> None:
        """Автор из запроса, запись в аудит и пересоздание инстанса с аннотациями."""
        serializer.save(created_by=self.request.user)
        workflow_audit_service.record(
            instance=serializer.instance,
            change_type=WorkflowChangeType.CREATED,
            changed_by=self.request.user,
        )
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)
