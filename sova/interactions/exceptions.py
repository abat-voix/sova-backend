class NoActiveResponsibleError(Exception):
    """У взаимодействия нет действующего ответственного, которого можно снять."""


class ManagerNotFoundError(Exception):
    """ФИО менеджера из договора не совпадает ни с одним активным пользователем."""


class AmbiguousManagerError(Exception):
    """ФИО менеджера из договора совпадает с несколькими активными пользователями."""


class ContractAlreadyAttachedError(Exception):
    """Договор уже привязан к взаимодействию — привязать его повторно нельзя."""
