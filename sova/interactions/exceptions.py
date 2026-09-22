from rest_framework import status
from rest_framework.exceptions import APIException


class ContactLinkError(APIException):
    """Ошибка проверки привязки контакта к взаимодействию."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Контакт нельзя привязать к взаимодействию."
    default_code = "contact_link_conflict"

    def __init__(self, code: str, detail: str, status_code: int | None = None):
        self.error_code = code
        self.status_code = status_code or self.status_code
        super().__init__(detail=detail, code=code)


class NoActiveResponsibleError(Exception):
    """У взаимодействия нет действующего ответственного, которого можно снять."""
