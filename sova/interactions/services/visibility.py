from django.db.models import Exists, OuterRef, Q, QuerySet

from accounts.models import SystemRole
from accounts.services import get_system_role
from sova.interactions.models import Interaction, Responsible


def visible_interactions(user) -> QuerySet[Interaction]:
    """
    Взаимодействия, которые видит `user` согласно своей роли в СОВА.

    КАМ видит взаимодействия, где он действующий ответственный; руководитель — свои, КАМов своей команды и КАМов
    без руководителя; администратор платформы — все. Взаимодействие без действующего ответственного ничьё и видно
    всем ролям: иначе его некому было бы разобрать, в том числе сразу после создания.
    Пользователь без прикладной роли не видит ничего.
    """
    role = get_system_role(user)

    if role == SystemRole.PLATFORM_ADMIN:
        return Interaction.objects.all()
    if role not in (SystemRole.KAM, SystemRole.HEAD):
        return Interaction.objects.none()

    assigned = Responsible.objects.filter(interaction=OuterRef("pk"), unassigned_at__isnull=True)
    own = Q(manager=user)
    if role == SystemRole.HEAD:
        # Роль КАМа проверяется и для команды: связь, устаревшая после смены роли в обход сервиса, не учитывается
        own |= Q(manager__system_role__role=SystemRole.KAM) & (
            Q(manager__supervision__head=user) | Q(manager__supervision__isnull=True)
        )

    return Interaction.objects.filter(Exists(assigned.filter(own)) | ~Exists(assigned))
