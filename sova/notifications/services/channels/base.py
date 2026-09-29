import abc
import logging

from sova.notifications.services.links import absolute_link
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

    def _text_with_link(self, message: Message) -> str:
        """Текст для внешнего канала: полная ссылка на объект отдельным абзацем в конце, если она есть."""
        link = absolute_link(message.link)
        return f"{message.text}\n\n{link}" if link else message.text

    def _chunks(self, text: str, limit: int) -> list[str]:
        """
        Делит text на части не длиннее limit по границам строк — для мессенджеров с лимитом длины сообщения.

        Строка длиннее limit режется по limit.
        """
        chunks: list[str] = []
        current = ""
        for line in text.split("\n"):
            for piece in [line[start : start + limit] for start in range(0, len(line), limit)] or [""]:
                candidate = f"{current}\n{piece}" if current else piece
                if len(candidate) > limit:
                    chunks.append(current)
                    candidate = piece
                current = candidate
        chunks.append(current)
        return [chunk.strip("\n") for chunk in chunks if chunk.strip()]
