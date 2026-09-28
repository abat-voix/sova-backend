from rest_framework import serializers

from sova.training.exceptions import TrainingError
from sova.training.models import TrainingApplicationLearner
from sova.training.services.payment import training_payment_service


class TrainingPaymentSerializer(serializers.Serializer):
    """
    Строка данных оплат (JSON оплат, интеграция): по ней находится участник заявки потока и отмечается оплата.

    Сопоставление — в `validate`, чтобы ненайденный или неоднозначный обучающийся был ошибкой валидации;
    `save()` возвращает участника заявки с `is_paid=True`.
    """

    stream = serializers.CharField(label="Номер потока", help_text="id потока (UUID)")
    course = serializers.CharField(label="Курс", help_text="Название программы потока")
    last_name = serializers.CharField(label="Фамилия")
    first_name = serializers.CharField(label="Имя")
    middle_name = serializers.CharField(label="Отчество", required=False, allow_blank=True, default="")
    email = serializers.CharField(label="Email", required=False, allow_blank=True, default="")
    phone = serializers.CharField(label="Телефон", required=False, allow_blank=True, default="")

    def validate(self, attrs: dict) -> dict:
        try:
            attrs["participant"] = training_payment_service.find_participant(
                stream_id=attrs["stream"],
                course=attrs["course"],
                last_name=attrs["last_name"],
                first_name=attrs["first_name"],
                middle_name=attrs["middle_name"],
                email=attrs["email"],
                phone=attrs["phone"],
            )
        except TrainingError as error:
            raise serializers.ValidationError(str(error.detail)) from error
        return attrs

    def create(self, validated_data: dict) -> TrainingApplicationLearner:
        return training_payment_service.mark_paid(validated_data["participant"])
