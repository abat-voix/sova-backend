import copy

from django.core.exceptions import FieldDoesNotExist
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import BaseConstraint, Model
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.settings import api_settings

from sova.core.models import NormalizedTextFieldsMixin


def validate_exactly_one_counterparty(
    attrs: dict,
    instance: Model | None,
) -> None:
    """
    Проверяет, что задан ровно один контрагент: организация или B2C-клиент.

    Правило дублирует CheckConstraint модели, чтобы клиент получал 400 с
    понятным сообщением, а не ошибку БД. При частичном обновлении (PATCH)
    недостающие в `attrs` значения берутся из `instance`.
    """
    organization = attrs.get("organization", getattr(instance, "organization", None))
    b2c_client = attrs.get("b2c_client", getattr(instance, "b2c_client", None))

    if (organization is None) == (b2c_client is None):
        raise serializers.ValidationError(
            _("Необходимо указать ровно одного контрагента: организацию или B2C-клиента."),
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


def validate_model_constraints(
    model: type[Model],
    attrs: dict,
    instance: Model | None = None,
) -> None:
    """
    Проверяет `Meta.constraints` модели на данных запроса и превращает нарушения в 400.

    DRF сам проверяет только уникальность по полям, а ограничения по выражениям (например,
    `UniqueConstraint(Lower("name"))` — уникальность без учёта регистра) без этой проверки доходят до
    БД и возвращаются как 409. Текстовые поля нормализуются так же, как при сохранении
    (`NormalizedTextFieldsMixin`), поэтому «ЯНДЕКС» с неразрывным пробелом — дубль «Яндекс».
    Проверяется копия объекта с применёнными `attrs` — исходный `instance` не меняется.
    """
    candidate = copy.copy(instance) if instance is not None else model()
    for field_name, value in attrs.items():
        try:
            field = model._meta.get_field(field_name)
        except FieldDoesNotExist:
            continue
        if not field.many_to_many:
            setattr(candidate, field_name, value)
    if isinstance(candidate, NormalizedTextFieldsMixin):
        candidate.normalize_text_fields()

    errors: dict[str, list[str]] = {}
    for constraint in model._meta.constraints:
        try:
            constraint.validate(model, candidate)
        except DjangoValidationError as error:
            errors.setdefault(_constraint_error_field(constraint), []).extend(error.messages)
    if errors:
        raise serializers.ValidationError(errors)


def _constraint_error_field(constraint: BaseConstraint) -> str:
    """Поле, к которому привязать ошибку ограничения: текстовое поле под Lower() или единственное поле."""
    for expression in getattr(constraint, "expressions", ()):
        if isinstance(expression, Lower):
            return expression.source_expressions[0].name
    fields = getattr(constraint, "fields", ())
    return fields[0] if len(fields) == 1 else api_settings.NON_FIELD_ERRORS_KEY
