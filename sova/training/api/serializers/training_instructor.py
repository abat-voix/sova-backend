from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers import (
    B2CClientShortSerializer,
    DirectionShortSerializer,
    ProgramShortSerializer,
    OrganizationShortSerializer,
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
    """Преподаватель — валидация входных данных; место работы ровно одно: организация или B2C-клиент."""

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
        return attrs
