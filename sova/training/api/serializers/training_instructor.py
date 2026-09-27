from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers import (
    B2CClientShortSerializer,
    DirectionShortSerializer,
    ProgramShortSerializer,
    UniversityShortSerializer,
)
from sova.training.models import TrainingInstructor


class TrainingInstructorShortSerializer(serializers.ModelSerializer):
    """Преподаватель — кратко, для потока."""

    class Meta:
        model = TrainingInstructor
        fields = ("id", "full_name", "position")


class TrainingInstructorSerializer(serializers.ModelSerializer):
    """Преподаватель — представление для чтения (list/retrieve)."""

    university = UniversityShortSerializer(read_only=True, label=_("Вуз"))
    b2c_client = B2CClientShortSerializer(read_only=True, label=_("B2C-клиент"))
    directions = DirectionShortSerializer(many=True, read_only=True, label=_("Направления"))
    programs = ProgramShortSerializer(many=True, read_only=True, label=_("Программы"))

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
            "university",
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
    """Преподаватель — валидация входных данных; организация ровно одна: вуз или B2C-клиент."""

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
            "university",
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
        university = attrs.get("university", getattr(self.instance, "university", None))
        b2c_client = attrs.get("b2c_client", getattr(self.instance, "b2c_client", None))
        if (university is None) == (b2c_client is None):
            raise serializers.ValidationError(
                {"university": [_("Укажите ровно одну организацию: вуз или B2C-клиента.")]}
            )
        return attrs
