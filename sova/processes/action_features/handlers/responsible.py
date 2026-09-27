from rest_framework import serializers

from accounts.exceptions import KamHasHeadError
from sova.interactions.exceptions import NoActiveResponsibleError
from sova.interactions.models import Responsible
from sova.interactions.services import assignment_candidates, responsible_service
from sova.interactions.services.responsible_policy import (
    assignable_managers,
    removable_managers,
)
from sova.processes.action_features.base import ActionFeatureResult
from sova.processes.action_features.errors import ActionFeatureError


def _manager_id(data: dict) -> int:
    try:
        return serializers.IntegerField(required=True, min_value=1).run_validation(
            data.get("manager"),
        )
    except serializers.ValidationError as error:
        raise ActionFeatureError(
            "invalid_manager",
            "Укажите корректный идентификатор ответственного.",
            400,
        ) from error


def _manager_data(manager) -> dict:
    return {
        "id": manager.pk,
        "full_name": manager.get_full_name() or manager.get_username(),
        "email": manager.email,
    }


def _target_data(responsible: Responsible) -> dict:
    manager = _manager_data(responsible.manager)
    return {
        "full_name": manager["full_name"],
        "manager": manager,
        "assigned_at": responsible.assigned_at.isoformat(),
        "unassigned_at": (
            responsible.unassigned_at.isoformat()
            if responsible.unassigned_at is not None
            else None
        ),
    }


class AssignResponsibleHandler:
    code = "responsible.assign"

    def initial(self, *, context, settings: dict) -> dict:
        candidates = assignment_candidates(
            interaction=context.interaction,
            actor=context.user,
        )
        return {
            "managers": [
                {
                    **_manager_data(candidate.manager),
                    "from_registry": candidate.from_registry,
                }
                for candidate in candidates
                if candidate.assignable and not candidate.is_responsible
            ],
        }

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        manager_id = _manager_id(data)
        manager = assignable_managers(context.user).filter(pk=manager_id).first()
        if manager is None:
            raise ActionFeatureError(
                "manager_not_assignable",
                "Этого менеджера нельзя назначить ответственным.",
                400,
            )
        try:
            responsible, _created = responsible_service.assign_by(
                interaction=context.interaction,
                manager=manager,
                actor=context.user,
            )
        except KamHasHeadError as error:
            raise ActionFeatureError(
                "kam_has_head",
                "У КАМа уже есть другой руководитель.",
                409,
            ) from error
        return ActionFeatureResult(
            "responsible",
            responsible.pk,
            _target_data(responsible),
        )


class UnassignResponsibleHandler:
    code = "responsible.unassign"

    def initial(self, *, context, settings: dict) -> dict:
        removable_ids = removable_managers(context.user).values_list("pk", flat=True)
        responsibles = (
            Responsible.objects.filter(
                interaction=context.interaction,
                manager_id__in=removable_ids,
                unassigned_at__isnull=True,
            )
            .select_related("manager")
            .order_by("assigned_at", "pk")
        )
        return {
            "managers": [_manager_data(item.manager) for item in responsibles],
        }

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        manager_id = _manager_id(data)
        manager = removable_managers(context.user).filter(pk=manager_id).first()
        if manager is None:
            raise ActionFeatureError(
                "manager_not_removable",
                "Этого менеджера нельзя снять с ответственных.",
                400,
            )
        try:
            responsible = responsible_service.unassign(
                interaction=context.interaction,
                manager=manager,
            )
        except NoActiveResponsibleError as error:
            raise ActionFeatureError(
                "no_active_responsible",
                "Менеджер не назначен ответственным за взаимодействие.",
                409,
            ) from error
        responsible.refresh_from_db()
        return ActionFeatureResult(
            "responsible",
            responsible.pk,
            _target_data(responsible),
        )
