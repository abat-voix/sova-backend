from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.masks import mask_email, mask_phone
from sova.training.models import Learner, TrainingApplicationLearner


class LearnerSerializer(serializers.ModelSerializer):
    """Обучающийся — чтение: email и телефон замаскированы, полные данные — `personal-data/`."""

    email = serializers.SerializerMethodField(label=_("Email"))
    phone = serializers.SerializerMethodField(label=_("Телефон"))

    class Meta:
        model = Learner
        fields = (
            "id",
            "full_name",
            "last_name",
            "first_name",
            "middle_name",
            "email",
            "phone",
            "consent_at",
            "is_active",
            "created_at",
            "updated_at",
        )

    def get_email(self, obj: Learner) -> str:
        return mask_email(obj.email)

    def get_phone(self, obj: Learner) -> str:
        return mask_phone(obj.phone)


class LearnerParticipationSerializer(serializers.ModelSerializer):
    """Участие обучающегося в заявке и признак зачисления."""

    application_number = serializers.CharField(source="application.number", read_only=True)
    stream = serializers.UUIDField(source="application.stream_id", read_only=True)
    stream_name = serializers.CharField(source="application.stream.name", read_only=True, default="")
    is_enrolled = serializers.BooleanField(read_only=True, label=_("Зачислен"))

    class Meta:
        model = TrainingApplicationLearner
        fields = ("id", "application", "application_number", "stream", "stream_name", "is_paid", "is_enrolled")


class LearnerDetailSerializer(LearnerSerializer):
    """Обучающийся с участиями в заявках видимых потоков."""

    participations = LearnerParticipationSerializer(many=True, read_only=True, label=_("Участие в заявках"))

    class Meta(LearnerSerializer.Meta):
        fields = (*LearnerSerializer.Meta.fields, "participations")
