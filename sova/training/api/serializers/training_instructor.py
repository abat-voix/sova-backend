from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers import (
    B2CClientShortSerializer,
    DirectionShortSerializer,
    OrganizationShortSerializer,
    ProgramWithDirectionSerializer,
)
from sova.training.models import TrainingInstructor


class TrainingInstructorShortSerializer(serializers.ModelSerializer):
    """Преподаватель — кратко, для потока."""

    class Meta:
        model = TrainingInstructor
        fields = ("id", "full_name", "position")


class TrainingInstructorSerializer(serializers.ModelSerializer):
    """Преподаватель — представление для чтения (list/retrieve)."""

    organization = OrganizationShortSerializer(read_only=True, label=_("Организация"))
    b2c_client = B2CClientShortSerializer(read_only=True, label=_("B2C-клиент"))
    directions = DirectionShortSerializer(many=True, read_only=True, label=_("Направления"))
    programs = ProgramWithDirectionSerializer(many=True, read_only=True, label=_("Программы"))

    class Meta:
        model = TrainingInstructor
        fields = (
            "id",
            "full_name",
            "last_name",
            "first_name",
            "middle_name",
            "email",
            "phone",
            "telegram",
            "organization",
            "b2c_client",
            "department",
            "position",
            "academic_degree",
            "academic_title",
            "teaching_experience_years",
            "education",
            "directions",
            "programs",
            "lms_external_id",
            "is_active",
            "comment",
            "created_at",
            "updated_at",
        )


class WriteTrainingInstructorSerializer(serializers.ModelSerializer):
    """
    Преподаватель — валидация входных данных; место работы ровно одно: организация или B2C-клиент.

    Компетенции — направления и их программы: программа выбирается только из выбранных направлений.
    """

    class Meta:
        model = TrainingInstructor
        fields = (
            "id",
            "last_name",
            "first_name",
            "middle_name",
            "email",
            "phone",
            "telegram",
            "organization",
            "b2c_client",
            "department",
            "position",
            "academic_degree",
            "academic_title",
            "teaching_experience_years",
            "education",
            "directions",
            "programs",
            "lms_external_id",
            "is_active",
            "comment",
        )

    def validate(self, attrs):
        organization = attrs.get("organization", getattr(self.instance, "organization", None))
        b2c_client = attrs.get("b2c_client", getattr(self.instance, "b2c_client", None))
        if (organization is None) == (b2c_client is None):
            raise serializers.ValidationError(
                {"organization": [_("Укажите ровно одно место работы: организацию или B2C-клиента.")]}
            )
        self._validate_programs(attrs)
        return attrs

    def _validate_programs(self, attrs: dict) -> None:
        """Каждая программа — из выбранных направлений: без направления её не отличить от тёзки из другого."""
        if "directions" not in attrs and "programs" not in attrs:
            return
        directions = attrs.get("directions")
        if directions is None:
            directions = list(self.instance.directions.all()) if self.instance else []
        programs = attrs.get("programs")
        if programs is None:
            programs = list(self.instance.programs.all()) if self.instance else []
        direction_ids = {direction.pk for direction in directions}
        foreign = [program.name for program in programs if program.direction_id not in direction_ids]
        if foreign:
            raise serializers.ValidationError(
                {
                    "programs": [
                        _("Программы не относятся к выбранным направлениям: %s.")
                        % ", ".join(f"«{name}»" for name in foreign)
                    ]
                }
            )
