from django.db import transaction
from django.utils import timezone

from sova.processes.action_features.context import build_context
from sova.processes.action_features.errors import ActionFeatureError
from sova.processes.action_features.registry import FEATURE_HANDLERS
from sova.processes.enum import ActionInstanceStatus
from sova.processes.models import ActionFeatureExecution
from sova.workflows.models import ActionFeature


@transaction.atomic
def execute_action_feature(*, action_instance, feature_code: str, user, data: dict) -> ActionFeatureExecution:
    try:
        feature = ActionFeature.objects.select_for_update().get(
            action_id=action_instance.action_id, code=feature_code, is_active=True,
        )
    except ActionFeature.DoesNotExist as error:
        raise ActionFeatureError("feature_not_configured", "Feature не настроен для действия.", 404) from error
    if action_instance.status != ActionInstanceStatus.IN_PROGRESS:
        raise ActionFeatureError("invalid_action_state", "Feature доступен только для действия в работе.")
    handler = FEATURE_HANDLERS.get(feature_code)
    if handler is None:
        raise ActionFeatureError("feature_not_implemented", "Обработчик feature ещё не реализован.")
    context = build_context(action_instance=action_instance, user=user)
    if context is None:
        raise ActionFeatureError("invalid_action_context")
    result = handler.execute(context=context, data=data, settings=feature.settings)
    execution = ActionFeatureExecution.objects.create(
        action_instance=action_instance,
        feature=feature,
        feature_code_snapshot=feature_code,
        target_type=result.target_type,
        target_id=result.target_id,
        performed_by=user,
        result=result.data,
    )
    execution.target = result
    return execution


def get_action_feature_initial(*, action_instance, feature_code: str, user) -> dict:
    """Начальные данные формы feature: то, что backend знает о контексте действия."""
    feature = ActionFeature.objects.filter(
        action_id=action_instance.action_id, code=feature_code, is_active=True,
    ).first()
    if feature is None:
        raise ActionFeatureError("feature_not_configured", "Feature не настроен для действия.", 404)
    if action_instance.status != ActionInstanceStatus.IN_PROGRESS:
        raise ActionFeatureError("invalid_action_state", "Feature доступен только для действия в работе.")
    handler = FEATURE_HANDLERS.get(feature_code)
    if handler is None or not hasattr(handler, "initial"):
        raise ActionFeatureError("feature_initial_not_supported", "У feature нет начальных данных.", 404)
    context = build_context(action_instance=action_instance, user=user)
    if context is None:
        raise ActionFeatureError("invalid_action_context")
    return handler.initial(context=context, settings=feature.settings)
