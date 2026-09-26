from django.db.models import Exists, OuterRef, Q, QuerySet

from accounts.models import SystemRole
from accounts.policy import Scope, visible_queryset
from sova.interactions.models import Contract, Interaction, Responsible


def visible_interactions(user) -> QuerySet[Interaction]:
    """
    Взаимодействия, которые видит `user` согласно своей роли в СОВА (область — `accounts.policy.READ_SCOPES`).

    КАМ видит взаимодействия, где он действующий ответственный; руководитель — свои, КАМов своей команды и КАМов
    без руководителя; администратор платформы, наблюдатель и superuser — все. Взаимодействие без действующего
    ответственного ничьё и видно всем ролям: иначе его некому было бы разобрать, в том числе сразу после создания.
    Пользователь без прикладной роли не видит ничего.
    """
    return visible_queryset(user, "interactions")


def visible_contracts(user) -> QuerySet[Contract]:
    """
    Договоры, которые видит `user`: договоры видимых ему взаимодействий и headless-договоры импорта реестра.

    Headless-договор виден по его ответственным тем же правилом, что взаимодействие: КАМу — свой, руководителю —
    свои, КАМов своей команды и КАМов без руководителя, администратору, наблюдателю и superuser — все; договор без
    действующих ответственных ничей и виден всем ролям. Пользователь без прикладной роли не видит ничего.
    """
    return visible_queryset(user, "contracts")


def interactions_in_scope(user, scope: Scope | None) -> QuerySet[Interaction]:
    """Взаимодействия в области `scope` пользователя `user` — правило раздела для `accounts.policy`."""
    if scope == Scope.ALL:
        return Interaction.objects.all()
    if scope is None:
        return Interaction.objects.none()
    return Interaction.objects.filter(_owned_or_unassigned(user=user, scope=scope, owner="interaction"))


def contracts_in_scope(user, scope: Scope | None) -> QuerySet[Contract]:
    """Договоры в области `scope` пользователя `user` — правило раздела для `accounts.policy`."""
    if scope == Scope.ALL:
        return Contract.objects.all()
    if scope is None:
        return Contract.objects.none()
    headless = Q(interaction__isnull=True) & _owned_or_unassigned(user=user, scope=scope, owner="contract")
    return Contract.objects.filter(Q(interaction__in=visible_interactions(user)) | headless)


def _owned_or_unassigned(user, scope: Scope, owner: str) -> Q:
    """
    Условие «объект свой или ничей» по действующим ответственным объекта; для `Scope.TEAM` своими считаются и
    объекты КАМов команды пользователя и свободных КАМов.

    `owner` — поле `Responsible`, указывающее на объект выборки (`interaction` или `contract`).
    """
    assigned = Responsible.objects.filter(**{owner: OuterRef("pk")}, unassigned_at__isnull=True)
    own = Q(manager=user)
    if scope == Scope.TEAM:
        # Роль КАМа проверяется и для команды: связь, устаревшая после смены роли в обход сервиса, не учитывается
        own |= Q(manager__system_role__role=SystemRole.KAM) & (
            Q(manager__supervision__head=user) | Q(manager__supervision__isnull=True)
        )
    return Q(Exists(assigned.filter(own))) | Q(~Exists(assigned))
