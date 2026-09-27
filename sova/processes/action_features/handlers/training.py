from rest_framework import serializers

from sova.interactions.models import Contract, InteractionProgram
from sova.processes.action_features.base import ActionFeatureResult
from sova.processes.action_features.errors import ActionFeatureError
from sova.training.exceptions import TrainingError
from sova.training.models import TrainingInstructor
from sova.training.services.stream import training_stream_service


class CreateTrainingStreamPayloadSerializer(serializers.Serializer):
    """Форма создания потока; программа и преподаватели проверяются по контексту действия в обработчике."""

    interaction_program = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=255)
    starts_at = serializers.DateField(required=False, allow_null=True, default=None)
    ends_at = serializers.DateField(required=False, allow_null=True, default=None)
    instructors = serializers.ListField(child=serializers.UUIDField(), default=list)

    def validate(self, attrs):
        if attrs["starts_at"] and attrs["ends_at"] and attrs["ends_at"] < attrs["starts_at"]:
            raise serializers.ValidationError({"ends_at": ["Окончание раньше начала."]})
        return attrs


def _programs(context):
    """Программы, по которым действие может создать поток: на этапе программы — только она."""
    if context.interaction_program is not None:
        return InteractionProgram.objects.filter(pk=context.interaction_program.pk, is_active=True)
    return (
        InteractionProgram.objects
        .filter(interaction=context.interaction, is_active=True)
        .select_related("program__direction")
        .order_by("added_at")
    )


def _instructors(context):
    """Активные преподаватели организации-контрагента взаимодействия."""
    return TrainingInstructor.objects.filter(
        university=context.university,
        b2c_client=context.b2c_client,
        is_active=True,
    )


class CreateTrainingStreamHandler:
    """
    Создаёт поток обучения по программе взаимодействия («Создать обучение»).

    Поток — отдельная сущность, а не этап workflow: кнопка ставится на действие после подписания договора.
    """

    code = "training.create"

    def initial(self, *, context, settings: dict) -> dict:
        return {
            "programs": [
                {"id": str(item.pk), "name": item.program.name, "direction": item.program.direction.name}
                for item in _programs(context).select_related("program__direction")
            ],
            "has_signed_contract": Contract.objects.filter(
                interaction=context.interaction, signed_at__isnull=False
            ).exists(),
            "instructors": [
                {"id": str(item.pk), "full_name": item.full_name, "position": item.position}
                for item in _instructors(context)
            ],
            "stream": {"name": "", "starts_at": None, "ends_at": None},
        }

    def execute(self, *, context, data: dict, settings: dict) -> ActionFeatureResult:
        serializer = CreateTrainingStreamPayloadSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        program_id = payload.get("interaction_program") or getattr(context.interaction_program, "pk", None)
        program = _programs(context).filter(pk=program_id).first() if program_id else None
        if program is None:
            raise serializers.ValidationError(
                {"interaction_program": ["Выберите активную программу этого взаимодействия."]}
            )
        instructors = list(TrainingInstructor.objects.filter(pk__in=payload["instructors"]))
        if len(instructors) != len(set(payload["instructors"])):
            raise serializers.ValidationError({"instructors": ["Преподаватель не найден."]})

        try:
            stream = training_stream_service.create_training_stream(
                interaction_program=program,
                name=payload["name"],
                starts_at=payload["starts_at"],
                ends_at=payload["ends_at"],
                instructors=instructors,
                user=context.user,
            )
        except TrainingError as error:
            raise ActionFeatureError(error.error_code, str(error.detail)) from error
        return ActionFeatureResult(
            "training_stream",
            stream.pk,
            {
                "name": stream.name,
                "interaction_program": str(program.pk),
                "program": program.program.name,
                "instructors": [str(item.pk) for item in instructors],
            },
        )
