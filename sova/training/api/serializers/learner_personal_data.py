from rest_framework import serializers

from sova.training.models import LearnerPersonalData


class LearnerPersonalDataSerializer(serializers.ModelSerializer):
    """Полные персональные данные — только администратору платформы, каждая выдача пишется в журнал."""

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
