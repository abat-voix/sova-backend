import rules
from rules import predicate


@predicate
def is_assigned_manager(user, instance) -> bool:
    """
    Пользователь — активный КАМ контрагента (вуза или B2C-клиента), к которому
    относится WorkflowInstance.

    Роль (Group/Permission) здесь ни при чём — это чисто объектная проверка:
    "относится ли именно этот процесс workflow к контрагенту, за которого
    назначен именно этот пользователь" (через ResponsibleAssignment,
    counterparty.current_responsible). Interaction.university и .b2c_client
    взаимоисключающие (см. constraint на Interaction), поэтому ровно одна из
    двух веток сработает.
    """
    if instance is None:
        return False

    interaction = instance.interaction
    if interaction.university_id is not None:
        counterparty = interaction.university
    elif interaction.b2c_client_id is not None:
        counterparty = interaction.b2c_client
    else:
        return False

    responsible = counterparty.current_responsible
    return responsible is not None and responsible.manager_id == user.id


def has_permission(codename: str):
    """
    Predicate-фабрика поверх обычного Django-права.

    Роль как данные (Group/Permission) не заменяется — has_permission просто
    даёт этому источнику правды точку входа в composable-предикаты rules,
    чтобы комбинировать его с объектными проверками вроде is_assigned_manager.
    """
    return predicate(lambda user, obj=None: user.has_perm(codename))


can_transition_backward = has_permission("crm.can_transition_backward")

# Переход по workflow разрешён активному КАМу вуза сделки ИЛИ тому, у чьей роли
# явно есть право на такой переход (например, "Руководитель" с can_transition_backward).
rules.add_perm("workflow.transition", is_assigned_manager | can_transition_backward)
