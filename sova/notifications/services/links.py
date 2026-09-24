from urllib.parse import urlencode
from uuid import UUID


def interaction_link(
    interaction_id: UUID,
    process_id: UUID | None = None,
    stage_id: UUID | None = None,
    action_id: UUID | None = None,
) -> str:
    """
    Адрес взаимодействия в интерфейсе с открытым процессом, этапом или действием.

    Формат согласован с фронтом: страница /interactions читает параметры interaction, process, stage, action.
    Адрес относительный — фронт переходит только по ссылкам внутри приложения.
    """
    params = {"interaction": interaction_id, "process": process_id, "stage": stage_id, "action": action_id}
    return "/interactions?" + urlencode({name: value for name, value in params.items() if value is not None})
