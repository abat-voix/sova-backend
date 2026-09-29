from urllib.parse import urlencode
from uuid import UUID

from django.conf import settings


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


def absolute_link(link: str) -> str:
    """Полный адрес относительной ссылки для внешних каналов; пусто — нет ссылки или не задан APP_PUBLIC_URL."""
    if not link or not settings.APP_PUBLIC_URL:
        return ""
    return settings.APP_PUBLIC_URL + link
