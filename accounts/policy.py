"""
Политика доступа СОВА — единственное место, где роль пользователя превращается в права.

Интерфейс:

- `can(user, action, resource=None)` — разрешена ли пользователю операция `action`, а с `resource` — ещё и над
  этой записью (запись должна входить в `visible_queryset` раздела);
- `visible_queryset(user, resource_type)` — записи раздела, которые пользователь видит;
- `allowed_actions(user)` — глобально разрешённые операции, их получает клиент для меню и кнопок.

Роли и операции сопоставлены явной таблицей `ROLE_ACTIONS`, область видимости раздела — таблицей `READ_SCOPES`.
Условия конкретной записи («своё», «команды») переводит в фильтр предметная функция раздела из `VISIBILITY_RULES`.
Django superuser проходит все прикладные проверки независимо от прикладной роли, но не обходит ограничения
целостности в предметных сервисах. Неактивный или анонимный пользователь, пользователь без роли и неизвестная
операция получают отказ.
"""

from enum import StrEnum

from django.db.models import Model, QuerySet
from django.utils.module_loading import import_string

from accounts.models import SystemRole
from accounts.services import get_system_role


class Action:
    """Стабильные коды прикладных операций; их же получает клиент в `/api/auth/me/`."""

    INTERACTIONS_READ = "interactions.read"
    INTERACTIONS_CREATE = "interactions.create"
    # Карточка взаимодействия, его состав (направления, программы, продукты) и контакты
    INTERACTIONS_UPDATE = "interactions.update"
    INTERACTIONS_DELETE = "interactions.delete"
    INTERACTIONS_RESPONSIBLES_ASSIGN = "interactions.responsibles.assign"
    INTERACTIONS_RESPONSIBLES_UNASSIGN = "interactions.responsibles.unassign"
    # Чат взаимодействия — переписка, а не просмотр взаимодействия: наблюдателю не положен
    INTERACTIONS_CHAT = "interactions.chat"


class Scope(StrEnum):
    """Область видимости записей раздела."""

    # Все записи
    ALL = "all"
    # Свои, КАМов своей команды, свободных КАМов и ничьи
    TEAM = "team"
    # Свои и ничьи
    OWN = "own"


_INTERACTIONS_WORK = frozenset(
    {
        Action.INTERACTIONS_READ,
        Action.INTERACTIONS_CREATE,
        Action.INTERACTIONS_UPDATE,
        Action.INTERACTIONS_DELETE,
        Action.INTERACTIONS_RESPONSIBLES_ASSIGN,
        Action.INTERACTIONS_CHAT,
    },
)

# Какие операции разрешены роли. Кого именно можно назначить или снять ответственным — `responsible_policy`
ROLE_ACTIONS: dict[str, frozenset[str]] = {
    SystemRole.OBSERVER: frozenset({Action.INTERACTIONS_READ}),
    SystemRole.KAM: _INTERACTIONS_WORK,
    SystemRole.HEAD: _INTERACTIONS_WORK | {Action.INTERACTIONS_RESPONSIBLES_UNASSIGN},
    SystemRole.PLATFORM_ADMIN: _INTERACTIONS_WORK | {Action.INTERACTIONS_RESPONSIBLES_UNASSIGN},
}

ALL_ACTIONS: frozenset[str] = frozenset().union(*ROLE_ACTIONS.values())

# Какие записи раздела видит роль. Роли нет в таблице — раздел ей не виден
READ_SCOPES: dict[str, dict[str, Scope]] = {
    "interactions": {
        SystemRole.OBSERVER: Scope.ALL,
        SystemRole.KAM: Scope.OWN,
        SystemRole.HEAD: Scope.TEAM,
        SystemRole.PLATFORM_ADMIN: Scope.ALL,
    },
    "contracts": {
        SystemRole.OBSERVER: Scope.ALL,
        SystemRole.KAM: Scope.OWN,
        SystemRole.HEAD: Scope.TEAM,
        SystemRole.PLATFORM_ADMIN: Scope.ALL,
    },
}

# Предметная функция раздела `(user, scope) -> QuerySet`; `scope=None` — раздел не виден.
# Пути, а не импорты: разделы сами зависят от `accounts`
VISIBILITY_RULES: dict[str, str] = {
    "interactions": "sova.interactions.services.visibility.interactions_in_scope",
    "contracts": "sova.interactions.services.visibility.contracts_in_scope",
}


def _is_active_account(user) -> bool:
    """Вошёл ли пользователь под действующей учётной записью."""
    return bool(user is not None and user.is_authenticated and user.is_active)


def effective_role(user) -> str | None:
    """
    Роль, по которой применяются предметные правила: superuser действует как администратор платформы.

    Неактивный и анонимный пользователь роли не имеют.
    """
    if not _is_active_account(user):
        return None
    if user.is_superuser:
        return SystemRole.PLATFORM_ADMIN
    return get_system_role(user)


def allowed_actions(user) -> frozenset[str]:
    """Операции, разрешённые пользователю без учёта конкретной записи."""
    if not _is_active_account(user):
        return frozenset()
    if user.is_superuser:
        return ALL_ACTIONS
    return ROLE_ACTIONS.get(get_system_role(user), frozenset())


def read_scope(user, resource_type: str) -> Scope | None:
    """Область видимости раздела для пользователя; `None` — раздел ему не виден."""
    role = effective_role(user)
    return READ_SCOPES[resource_type].get(role) if role else None


def visible_queryset(user, resource_type: str) -> QuerySet:
    """Записи раздела `resource_type`, которые видит пользователь."""
    rule = import_string(VISIBILITY_RULES[resource_type])
    return rule(user=user, scope=read_scope(user, resource_type))


def can(user, action: str, resource: Model | None = None) -> bool:
    """
    Разрешена ли пользователю операция `action`, а с `resource` — над этой записью.

    `resource` — запись основной модели раздела, к которому относится операция (раздел — префикс кода до точки):
    для `interactions.*` это `Interaction`. Запись вне видимости пользователя — отказ.
    """
    if action not in ALL_ACTIONS or action not in allowed_actions(user):
        return False
    if resource is None or user.is_superuser:
        return True
    resource_type = action.split(".", 1)[0]
    return visible_queryset(user, resource_type).filter(pk=resource.pk).exists()
