class NotConversationParticipantError(Exception):
    """Пользователь не участник беседы — не может ни читать, ни писать в неё."""


class SystemConversationIsReadOnlyError(Exception):
    """В системную беседу нельзя писать через пользовательский сценарий отправки."""
