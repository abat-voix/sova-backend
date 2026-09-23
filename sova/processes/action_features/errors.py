from rest_framework import status
from rest_framework.exceptions import APIException


class ActionFeatureError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "invalid_action_context"
    default_detail = "Feature невозможно выполнить в текущем контексте."

    def __init__(self, code: str, detail: str = "Feature невозможно выполнить.", status_code: int | None = None):
        self.status_code = status_code or self.status_code
        super().__init__(detail=detail, code=code)
