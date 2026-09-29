from dataclasses import dataclass

from sova.notifications.enum import NotificationKind


@dataclass(frozen=True)
class Message:
    """
    Сообщение для отправки по каналам.

    text — первая строка служит темой письма и заголовком уведомления в системе. kind — группа уведомления
    в системе. link — относительный адрес объекта в интерфейсе: колокольчик хранит его как есть, внешние
    каналы дописывают в конец текста полный адрес с APP_PUBLIC_URL.
    """

    text: str
    kind: str = NotificationKind.SYSTEM
    link: str = ""
