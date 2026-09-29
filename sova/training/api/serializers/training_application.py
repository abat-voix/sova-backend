from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.training.api.serializers.fields import VisibleStreamField
from sova.training.api.serializers.training_application_learner import TrainingApplicationLearnerSerializer
from sova.training.models import TrainingApplication


class TrainingApplicationSerializer(serializers.ModelSerializer):
    """Заявка — представление для чтения (list/retrieve)."""

    stream_name = serializers.CharField(source="stream.name", read_only=True, label=_("Поток"))
    participants = TrainingApplicationLearnerSerializer(many=True, read_only=True, label=_("Участники"))

    class Meta:
        model = TrainingApplication
        fields = (
            "id",
            "stream",
            "stream_name",
            "status",
            "comment",
            "participants",
            "created_by",
            "created_at",
            "updated_at",
        )


class WriteTrainingApplicationSerializer(serializers.ModelSerializer):
    """Заявка — создание по видимому потоку."""

    stream = VisibleStreamField()

    class Meta:
        model = TrainingApplication
        fields = ("id", "stream", "comment")


class UpdateTrainingApplicationSerializer(serializers.ModelSerializer):
    """Заявка — изменение: поток после создания не меняется."""

    class Meta:
        model = TrainingApplication
        fields = ("id", "comment")
