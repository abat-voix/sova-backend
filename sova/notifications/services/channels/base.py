import abc
import logging

from sova.notifications.services.message import Message

logger = logging.getLogger("django")


class NotificationChannelSender(abc.ABC):
    """Базовый класс отправителя уведомления по одному каналу."""

    # Предупреждение о пустом токене уже записано в лог этого процесса
    _is_missing_token_logged = False

    @abc.abstractmethod
    def send(self, target: str, message: Message) -> bool:
        """Отправляет message адресату target. Возвращает True при успехе, не поднимает исключений."""
        raise NotImplementedError

    def _warn_missing_token(self, setting_name: str) -> None:
        """Пишет в лог один раз за процесс, что канал не настроен и отправка по нему пропускается."""
        if self._is_missing_token_logged:
            return
        logger.warning("%s не задан — канал %s пропускается", setting_name, type(self).__name__)
        self._is_missing_token_logged = True
