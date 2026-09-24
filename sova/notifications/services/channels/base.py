import abc

from sova.notifications.services.message import Message


class NotificationChannelSender(abc.ABC):
    """Базовый класс отправителя уведомления по одному каналу."""

    @abc.abstractmethod
    def send(self, target: str, message: Message) -> bool:
        """Отправляет message адресату target. Возвращает True при успехе, не поднимает исключений."""
        raise NotImplementedError
