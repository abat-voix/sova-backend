from rest_framework import serializers

from sova.training.models import TrainingInstructorQualification


class TrainingInstructorQualificationSerializer(serializers.ModelSerializer):
    """Запись о подготовке преподавателя: обучение преподавателей или повышение квалификации."""

    class Meta:
        model = TrainingInstructorQualification
        fields = (
            "id",
            "instructor",
            "kind",
            "program",
            "interaction",
            "completed_at",
            "document_type",
            "document_number",
            "document_file",
            "valid_until",
            "comment",
            "created_by",
            "created_at",
        )
        read_only_fields = ("created_by", "created_at")
