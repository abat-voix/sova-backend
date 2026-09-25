from rest_framework import status
from rest_framework.exceptions import APIException


class AccountRuleError(APIException):
    """Изменение пользователя нарушает правило управления учётными записями (HTTP 400)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Изменение пользователя недопустимо."
    default_code = "invalid_account_change"
