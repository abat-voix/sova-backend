from django.db.models import QuerySet

from accounts.policy import Scope, visible_queryset
from sova.interactions.services.visibility import interactions_in_scope
from sova.training.models import TrainingApplication, TrainingApplicationLearner, TrainingStream


def visible_streams(user) -> QuerySet[TrainingStream]:
    """
    Потоки, которые видит `user` согласно своей роли (раздел `training` в `accounts.policy.READ_SCOPES`).

    Поток виден вместе со взаимодействием своей программы: КАМ — потоки своих взаимодействий, руководитель — своих
    и команды, администратор платформы и наблюдатель — все.
    """
    return visible_queryset(user, "training")


def visible_applications(user) -> QuerySet[TrainingApplication]:
    """Заявки потоков, видимых пользователю."""
    return TrainingApplication.objects.filter(stream__in=visible_streams(user))


def visible_application_learners(user) -> QuerySet[TrainingApplicationLearner]:
    """Участники заявок потоков, видимых пользователю."""
    return TrainingApplicationLearner.objects.filter(application__in=visible_applications(user))


def training_streams_in_scope(user, scope: Scope | None) -> QuerySet[TrainingStream]:
    """Потоки в области `scope` пользователя `user` — правило раздела `training` для `accounts.policy`."""
    if scope == Scope.ALL:
        return TrainingStream.objects.all()
    if scope is None:
        return TrainingStream.objects.none()
    return TrainingStream.objects.filter(
        interaction_program__interaction__in=interactions_in_scope(user=user, scope=scope)
    )
