from collections.abc import Iterable

from django.db import transaction
from django.db.models import Count, QuerySet
from rest_framework import serializers as drf_serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from sova.core.api.views import SovaBaseViewSet
from sova.workflows.api import filters, serializers
from sova.workflows.api.views.audit import WorkflowAuditMixin
from sova.workflows.enum import WorkflowChangeType
from sova.workflows.models import (
    ActionDependency,
    ActionOutcome,
    ActionTransition,
    StageTransition,
    Workflow,
    WorkflowAction,
    WorkflowStage,
)
from sova.workflows.api.permissions import CanManageWorkflows, can_edit_workflow
from sova.workflows.services import workflow_audit_service


class WorkflowViewSet(WorkflowAuditMixin, SovaBaseViewSet):
    """Шаблоны workflow. Доступны CRUD операции; правки пишутся в аудит."""

    read_serializer_class = serializers.WorkflowSerializer
    serializer_class = serializers.WriteWorkflowSerializer
    queryset = Workflow.objects.all()
    ordering_fields = "__all__"
    search_fields = ("name", "code", "description")
    filterset_class = filters.WorkflowFilter
    permission_classes = (CanManageWorkflows,)

    def get_queryset(self) -> QuerySet:
        """Queryset со счётчиком этапов."""
        return (
            super()
            .get_queryset()
            .select_related("created_by")
            .annotate(stages_count=Count("workflow_stages", distinct=True))
            .order_by("name")  # annotate() со GROUP BY сбрасывает Meta.ordering
        )

    def _definition(self, workflow: Workflow) -> dict:
        """Return the complete graph in one response for the editor."""
        from sova.workflows.api.serializers import (
            ActionDependencySerializer,
            ActionOutcomeSerializer,
            ActionTransitionSerializer,
            StageTransitionSerializer,
            WorkflowActionSerializer,
            WorkflowStageSerializer,
        )

        return {
            "workflow": self.get_response_serializer(workflow).data,
            "stages": WorkflowStageSerializer(
                workflow.workflow_stages.all(), many=True
            ).data,
            "actions": WorkflowActionSerializer(
                WorkflowAction.objects.filter(stage__workflow=workflow)
                .select_related("stage"),
                many=True,
            ).data,
            "outcomes": ActionOutcomeSerializer(
                ActionOutcome.objects.filter(action__stage__workflow=workflow)
                .select_related("action"),
                many=True,
            ).data,
            "stage_transitions": StageTransitionSerializer(
                StageTransition.objects.filter(from_stage__workflow=workflow)
                .select_related("from_stage", "to_stage"),
                many=True,
            ).data,
            "action_transitions": ActionTransitionSerializer(
                ActionTransition.objects.filter(outcome__action__stage__workflow=workflow)
                .select_related("outcome", "target_action"),
                many=True,
            ).data,
            "action_dependencies": ActionDependencySerializer(
                ActionDependency.objects.filter(action__stage__workflow=workflow)
                .select_related("action", "depends_on_action"),
                many=True,
            ).data,
        }

    def _validation_errors(self, workflow: Workflow) -> list[dict[str, str]]:
        """Validate graph invariants required before publication."""
        stages = list(workflow.workflow_stages.filter(is_active=True))
        actions = list(
            WorkflowAction.objects.filter(stage__workflow=workflow, is_active=True)
            .select_related("stage")
        )
        errors: list[dict[str, str]] = []

        initial = [stage for stage in stages if stage.is_initial]
        if not stages:
            errors.append({"code": "empty_workflow", "message": "Workflow должен содержать этапы."})
        if len(initial) != 1:
            errors.append({"code": "initial_stage_count", "message": "Должен быть ровно один начальный этап."})
        if stages and not any(stage.is_final for stage in stages):
            errors.append({"code": "missing_final_stage", "message": "Нужен хотя бы один финальный этап."})

        active_stage_ids = {stage.pk for stage in stages}
        stage_edges = list(
            StageTransition.objects.filter(
                from_stage_id__in=active_stage_ids,
                to_stage_id__in=active_stage_ids,
                is_active=True,
            ).values_list("from_stage_id", "to_stage_id")
        )
        if self._has_cycle(stage_edges):
            errors.append({"code": "stage_transition_cycle", "message": "Переходы этапов образуют цикл."})

        active_action_ids = {action.pk for action in actions}
        for action in actions:
            if not ActionOutcome.objects.filter(action=action, is_active=True).exists():
                errors.append({"code": "missing_action_outcome", "message": f"У действия «{action.name}» нет активного исхода."})

        dependency_edges = list(
            ActionDependency.objects.filter(
                action_id__in=active_action_ids,
                depends_on_action_id__in=active_action_ids,
                is_active=True,
            ).values_list("action_id", "depends_on_action_id")
        )
        if self._has_cycle(dependency_edges):
            errors.append({"code": "action_dependency_cycle", "message": "Зависимости действий образуют цикл."})

        return errors

    @staticmethod
    def _has_cycle(edges: Iterable[tuple]) -> bool:
        graph: dict[object, list[object]] = {}
        for source, target in edges:
            graph.setdefault(source, []).append(target)
        visiting: set[object] = set()
        visited: set[object] = set()

        def visit(node: object) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            if any(visit(child) for child in graph.get(node, ())):
                return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in graph)

    @action(detail=True, methods=["get", "put"], url_path="definition")
    def definition(self, request, pk=None):
        """Read or atomically update the complete workflow definition."""
        workflow = self.get_object()
        if request.method == "GET":
            return Response(self._definition(workflow))

        if not can_edit_workflow(request.user, workflow):
            return Response(
                {"detail": "Руководитель может изменять только созданные им workflow."},
                status=status.HTTP_403_FORBIDDEN,
            )
        payload = request.data
        required = (
            "workflow",
            "stages",
            "actions",
            "outcomes",
            "stage_transitions",
            "action_transitions",
            "action_dependencies",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise drf_serializers.ValidationError(
                {key: "Поле обязательно для полной схемы." for key in missing}
            )

        from sova.workflows.api.serializers import (
            WriteActionDependencySerializer,
            WriteActionOutcomeSerializer,
            WriteActionTransitionSerializer,
            WriteStageTransitionSerializer,
            WriteWorkflowActionSerializer,
            WriteWorkflowStageSerializer,
            WriteWorkflowSerializer,
        )

        write_workflow = WriteWorkflowSerializer(
            workflow, data=payload["workflow"], partial=True
        )
        write_workflow.is_valid(raise_exception=True)

        collections = (
            ("stages", WorkflowStage, WriteWorkflowStageSerializer),
            ("actions", WorkflowAction, WriteWorkflowActionSerializer),
            ("outcomes", ActionOutcome, WriteActionOutcomeSerializer),
            ("stage_transitions", StageTransition, WriteStageTransitionSerializer),
            ("action_transitions", ActionTransition, WriteActionTransitionSerializer),
            ("action_dependencies", ActionDependency, WriteActionDependencySerializer),
        )

        with transaction.atomic():
            write_workflow.save()
            keep: dict[str, set] = {}
            for key, _model, write_class in collections:
                queryset = self._definition_queryset(key, workflow)
                ids: set = set()
                for item in payload[key]:
                    item_id = item.get("id")
                    if not item_id:
                        raise drf_serializers.ValidationError(
                            {key: "Каждый элемент полной схемы должен содержать id."}
                        )
                    instance = queryset.filter(pk=item_id).first()
                    if instance is None:
                        raise drf_serializers.ValidationError(
                            {key: f"Элемент {item_id} не принадлежит workflow."}
                        )
                    serializer = write_class(instance, data=item, partial=True)
                    serializer.is_valid(raise_exception=True)
                    serializer.save()
                    ids.add(instance.pk)
                keep[key] = ids

            # Delete only after all references have been validated and updated.
            for key, _model, _write_class in reversed(collections):
                queryset = self._definition_queryset(key, workflow)
                queryset.exclude(pk__in=keep[key]).delete()

        workflow.refresh_from_db()
        return Response(self._definition(workflow))

    def _definition_queryset(self, key: str, workflow: Workflow):
        """Return one child collection scoped to the selected workflow."""
        relations = {
            "stages": WorkflowStage.objects.filter(workflow=workflow),
            "actions": WorkflowAction.objects.filter(stage__workflow=workflow),
            "outcomes": ActionOutcome.objects.filter(action__stage__workflow=workflow),
            "stage_transitions": StageTransition.objects.filter(from_stage__workflow=workflow),
            "action_transitions": ActionTransition.objects.filter(outcome__action__stage__workflow=workflow),
            "action_dependencies": ActionDependency.objects.filter(action__stage__workflow=workflow),
        }
        return relations[key]

    @action(detail=True, methods=["post"], url_path="validate")
    def validate_definition(self, request, pk=None):
        """Validate the current workflow graph before publication."""
        workflow = self.get_object()
        errors = self._validation_errors(workflow)
        return Response({"valid": not errors, "errors": errors})

    @action(detail=True, methods=["post"], url_path="publish")
    @transaction.atomic
    def publish(self, request, pk=None):
        """Publish a valid workflow."""
        workflow = self.get_object()
        if not can_edit_workflow(request.user, workflow):
            return Response(
                {"detail": "Руководитель может изменять только созданные им workflow."},
                status=status.HTTP_403_FORBIDDEN,
            )
        errors = self._validation_errors(workflow)
        if errors:
            return Response({"valid": False, "errors": errors}, status=status.HTTP_400_BAD_REQUEST)
        workflow.is_active = True
        workflow.save(update_fields=["is_active", "updated_at"])
        workflow_audit_service.record(
            instance=workflow,
            change_type=WorkflowChangeType.UPDATED,
            changed_by=request.user,
        )
        return Response(self.get_response_serializer(workflow).data)

    @action(detail=True, methods=["post"], url_path="unpublish")
    @transaction.atomic
    def unpublish(self, request, pk=None):
        """Return a workflow to draft state."""
        workflow = self.get_object()
        if not can_edit_workflow(request.user, workflow):
            return Response(
                {"detail": "Руководитель может изменять только созданные им workflow."},
                status=status.HTTP_403_FORBIDDEN,
            )
        workflow.is_active = False
        workflow.save(update_fields=["is_active", "updated_at"])
        workflow_audit_service.record(
            instance=workflow,
            change_type=WorkflowChangeType.UPDATED,
            changed_by=request.user,
        )
        return Response(self.get_response_serializer(workflow).data)

    @transaction.atomic
    def perform_create(self, serializer: serializers.WriteWorkflowSerializer) -> None:
        """Автор из запроса, запись в аудит и пересоздание инстанса с аннотациями."""
        # New workflows always start as drafts. Publication goes through the
        # validation-aware `/publish/` action.
        serializer.save(created_by=self.request.user, is_active=False)
        workflow_audit_service.record(
            instance=serializer.instance,
            change_type=WorkflowChangeType.CREATED,
            changed_by=self.request.user,
        )
        serializer.instance = self.get_queryset().get(pk=serializer.instance.pk)

    def perform_update(self, serializer) -> None:
        """Keep publication behind the validation-aware action."""
        if serializer.validated_data.get("is_active") is True and not serializer.instance.is_active:
            raise drf_serializers.ValidationError(
                {"is_active": "Для публикации используйте endpoint publish."}
            )
        super().perform_update(serializer)
