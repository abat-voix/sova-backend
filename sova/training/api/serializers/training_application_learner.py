from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.training.api.serializers.fields import VisibleApplicationField
from sova.training.api.serializers.learner import LearnerSerializer
from sova.training.models import Learner, TrainingApplicationLearner


class TrainingApplicationLearnerSerializer(serializers.ModelSerializer):
    """Участник заявки — представление для чтения: факт оплаты и зачисление."""

    learner = LearnerSerializer(read_only=True, label=_("Обучающийся"))
    is_enrolled = serializers.BooleanField(read_only=True, default=None, label=_("Зачислен"))

    class Meta:
        model = TrainingApplicationLearner
        fields = ("id", "application", "learner", "is_paid", "is_enrolled", "created_at", "updated_at")


class WriteTrainingApplicationLearnerSerializer(serializers.ModelSerializer):
    """Участник заявки — создание вручную (например, чтобы отметить оплату без загрузки JSON)."""

    application = VisibleApplicationField()
    learner = serializers.PrimaryKeyRelatedField(queryset=Learner.objects.all(), label=_("Обучающийся"))

    class Meta:
        model = TrainingApplicationLearner
        fields = ("id", "application", "learner", "is_paid")
        # Повтор участника проверяет сервис (409 learner_already_in_application), а не DRF-валидатор
        validators = []


class UpdateTrainingApplicationLearnerSerializer(serializers.ModelSerializer):
    """Участник заявки — изменение: только факт оплаты."""

    class Meta:
        model = TrainingApplicationLearner
        fields = ("id", "is_paid")
