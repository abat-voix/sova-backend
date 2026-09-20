import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


def validate_exactly_one_counterparty(
    attrs: dict,
    instance: Model | None,
) -> None:
    """
    Проверяет, что задан ровно один контрагент: вуз или B2C-клиент.

    Правило дублирует CheckConstraint модели, чтобы клиент получал 400 с
    понятным сообщением, а не ошибку БД. При частичном обновлении (PATCH)
    недостающие в `attrs` значения берутся из `instance`.
    """
    university = attrs.get("university", getattr(instance, "university", None))
    b2c_client = attrs.get("b2c_client", getattr(instance, "b2c_client", None))

    if (university is None) == (b2c_client is None):
        raise serializers.ValidationError(
            _("Необходимо указать ровно одного контрагента: вуз или B2C-клиента."),
        )


def validate_model_clean(
    model: type[Model],
    attrs: dict,
    instance: Model | None = None,
) -> None:
    """
    Вызывает `clean()` модели на данных запроса и превращает ошибку в 400.

    DRF не вызывает `Model.clean()` сам, а межполевые правила (принадлежность к
    одному взаимодействию и т.п.) живут именно там. Проверяется копия объекта с
    применёнными `attrs` — исходный `instance` не меняется.
    """
    candidate = copy.copy(instance) if instance is not None else model()
    for field_name, value in attrs.items():
        setattr(candidate, field_name, value)

    try:
        candidate.clean()
    except DjangoValidationError as error:
        if hasattr(error, "error_dict"):
            raise serializers.ValidationError(error.message_dict)
        raise serializers.ValidationError(error.messages)
