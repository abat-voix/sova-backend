import logging

from sova.notifications.models import Notification
from sova.notifications.services.channels.base import NotificationChannelSender
from sova.notifications.services.message import Message

logger = logging.getLogger("django")

TITLE_MAX_LENGTH = Notification._meta.get_field("title").max_length


class SystemChannelSender(NotificationChannelSender):
    """Уведомление в системе: запись Notification, которую пользователь видит в интерфейсе."""

    def send(self, target: int, message: Message) -> bool:
        """
        Сохраняет message пользователю с id target.

        Заголовок — первая строка text, текст — остальное; группа и ссылка — из message.
        """
        title, _, text = message.text.partition("\n")
        try:
            Notification.objects.create(
                recipient_id=target,
                title=title[:TITLE_MAX_LENGTH],
                text=text.strip(),
                kind=message.kind,
                link=message.link,
            )
        except Exception:
            # Ошибка БД не должна прерывать остальные каналы
            logger.exception("Не удалось сохранить уведомление в системе для пользователя %s", target)
            return False
        return True
