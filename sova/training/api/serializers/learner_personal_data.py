from rest_framework import serializers

from sova.training.models import LearnerPersonalData
from sova.training.services.personal_data_access import PersonalDataAccessService


class LearnerPersonalDataSerializer(serializers.ModelSerializer):
    """Полные персональные данные — КАМу, руководителю и админу; каждая выдача пишется в журнал."""

    email = serializers.CharField(source="learner.email", read_only=True)
    phone = serializers.CharField(source="learner.phone", read_only=True)
    birth_date = serializers.DateField(read_only=True)
    passport_issued_at = serializers.DateField(read_only=True)
    diploma_issued_at = serializers.DateField(read_only=True)

    class Meta:
        model = LearnerPersonalData
        exclude = ("snils_hash",)
        read_only_fields = [
            field.name for field in LearnerPersonalData._meta.concrete_fields if field.name != "snils_hash"
        ]


class WriteLearnerPersonalDataSerializer(serializers.ModelSerializer):
    """Правка персональных данных; частичная — меняются только переданные поля."""

    birth_date = serializers.DateField(required=False, allow_null=True)
    passport_issued_at = serializers.DateField(required=False, allow_null=True)
    diploma_issued_at = serializers.DateField(required=False, allow_null=True)

    class Meta:
        model = LearnerPersonalData
        fields = PersonalDataAccessService.FIELDS
