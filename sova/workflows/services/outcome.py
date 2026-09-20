from sova.workflows.models import ActionOutcome, WorkflowAction


class ActionOutcomeService:
    """
    Исходы действий workflow.

    Завершить действие можно только с исходом (`ActionResult.outcome` обязателен), поэтому
    каждое действие получает исход по умолчанию «Выполнено». Правила комментария и вложения
    администратор настраивает на самом исходе, а дополнительные исходы добавляет рядом.
    """

    DEFAULT_CODE = "done"
    DEFAULT_NAME = "Выполнено"

    def create_default(self, action: WorkflowAction) -> ActionOutcome:
        """
        Создаёт исход по умолчанию, если его ещё нет.

        Повторный вызов и уже настроенный исход с кодом по умолчанию не перезаписываются.
        """
        outcome, _ = ActionOutcome.objects.get_or_create(
            action=action,
            code=self.DEFAULT_CODE,
            defaults={"name": self.DEFAULT_NAME},
        )
        return outcome


action_outcome_service = ActionOutcomeService()
