from rest_framework import status
from rest_framework.exceptions import APIException


class TrainingError(APIException):
    """Операцию обучения нельзя выполнить в текущем состоянии данных; `error_code` — машиночитаемая причина."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Операцию обучения нельзя выполнить."
    default_code = "training_conflict"

    def __init__(self, code: str, detail: str, status_code: int | None = None):
        self.error_code = code
        self.status_code = status_code or self.status_code
        super().__init__(detail=detail, code=code)


class LearnerExistsError(TrainingError):
    """Обучающийся с такими контактами уже есть: второй не создаётся, в ответе — id найденного."""

    def __init__(self, learner):
        super().__init__(
            code="learner_exists",
            detail={
                "detail": f"Обучающийся с такими контактами уже есть: {learner.full_name}.",
                "learner": str(learner.pk),
            },
        )
