from dataclasses import dataclass

from sova.notifications.enum import NotificationKind


@dataclass(frozen=True)
class Message:
    """
    Сообщение для отправки по каналам.

    text — первая строка служит темой письма и заголовком уведомления в системе. kind и link нужны только
    системному каналу: группа уведомления и ссылка на объект в интерфейсе.
    """

    text: str
    kind: str = NotificationKind.SYSTEM
    link: str = ""
