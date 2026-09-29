from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers import ProgramShortSerializer
from sova.training.api.serializers.training_instructor import TrainingInstructorShortSerializer
from sova.training.models import TrainingInstructor, TrainingStream


class TrainingStreamSerializer(serializers.ModelSerializer):
    """Поток — представление для чтения; номер потока — `id`."""

    program = ProgramShortSerializer(source="interaction_program.program", read_only=True, label=_("Программа"))
    interaction = serializers.UUIDField(
        source="interaction_program.interaction_id",
        read_only=True,
        label=_("Взаимодействие"),
    )
    interaction_number = serializers.CharField(
        source="interaction_program.interaction.display_number",
        read_only=True,
        label=_("Номер взаимодействия"),
    )
    organization = serializers.UUIDField(
        source="interaction_program.interaction.organization_id",
        read_only=True,
        allow_null=True,
        label=_("Организация"),
        help_text=_("Контрагент взаимодействия; преподаватели назначаются только из его организации"),
    )
    b2c_client = serializers.UUIDField(
        source="interaction_program.interaction.b2c_client_id",
        read_only=True,
        allow_null=True,
        label=_("B2C-клиент"),
    )
    counterparty_name = serializers.SerializerMethodField(label=_("Контрагент"))
    instructors = TrainingInstructorShortSerializer(many=True, read_only=True, label=_("Преподаватели"))
    applications_count = serializers.IntegerField(read_only=True, default=None, label=_("Заявок"))
    participants_count = serializers.IntegerField(
        read_only=True,
        default=None,
        label=_("Участников"),
        help_text=_("Участники действующих заявок"),
    )
    paid_count = serializers.IntegerField(
        read_only=True,
        default=None,
        label=_("Оплатили"),
        help_text=_("Оплатившие участники действующих заявок"),
    )

    class Meta:
        model = TrainingStream
        fields = (
            "id",
            "name",
            "interaction_program",
            "interaction",
            "interaction_number",
            "organization",
            "b2c_client",
            "counterparty_name",
            "program",
            "starts_at",
            "ends_at",
            "status",
            "instructors",
            "applications_count",
            "participants_count",
            "paid_count",
            "created_by",
            "created_at",
            "updated_at",
        )


    def get_counterparty_name(self, obj: TrainingStream) -> str:
        interaction = obj.interaction_program.interaction
        counterparty = interaction.organization or interaction.b2c_client
        return getattr(counterparty, "name", None) or getattr(counterparty, "full_name", "")


class WriteTrainingStreamSerializer(serializers.ModelSerializer):
    """Поток — изменение; создаётся возможностью `training.create`."""

    class Meta:
        model = TrainingStream
        fields = ("id", "name", "starts_at", "ends_at", "status")

    def validate(self, attrs):
        starts_at = attrs.get("starts_at", self.instance.starts_at if self.instance else None)
        ends_at = attrs.get("ends_at", self.instance.ends_at if self.instance else None)
        if starts_at and ends_at and ends_at < starts_at:
            raise serializers.ValidationError({"ends_at": [_("Окончание раньше начала.")]})
        return attrs


class AssignTrainingInstructorSerializer(serializers.Serializer):
    """Назначение преподавателя на поток."""

    instructor = serializers.PrimaryKeyRelatedField(
        queryset=TrainingInstructor.objects.all(),
        label=_("Преподаватель"),
    )
