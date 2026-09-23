"""
Тестовые взаимодействия для разработки.

Наполняет пустую базу данными, на которых видно списки и ролевую видимость:
взаимодействия с вузами и B2C-клиентами, у каждого — действующий ответственный.
Вызывается командой `./manage.py loaddata --interactions`.
"""

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from sova.catalog.models import B2CClient, University
from sova.interactions.models import Interaction, Responsible

# Метка в комментарии: по ней видно, что взаимодействие тестовое, и считается уже созданное
SEED_COMMENT_PREFIX = "[seed]"
DEFAULT_COUNT = 10
B2C_RATIO = 0.3
MANAGER_EMAIL = "kam@kam.ru"


class SeedError(Exception):
    """В базе нет данных, без которых тестовые взаимодействия не создать."""


@dataclass
class SeedResult:
    """Итог наполнения: что создано и на кого назначено."""

    created: int
    with_universities: int
    with_b2c_clients: int
    existing: int
    manager: AbstractBaseUser


@transaction.atomic
def seed_interactions(count: int = DEFAULT_COUNT, manager_email: str = MANAGER_EMAIL) -> SeedResult:
    """
    Доводит число тестовых взаимодействий до `count`.

    Уже созданные считаются по метке в комментарии, поэтому повторный запуск лишних не плодит.
    Ответственным назначается пользователь с `manager_email`, а если такого нет — первый активный.
    """
    universities = list(University.objects.filter(is_active=True))
    if not universities:
        raise SeedError("В базе нет активных вузов — сначала загрузите справочники.")

    manager = _resolve_manager(manager_email=manager_email)
    if manager is None:
        raise SeedError("В базе нет активных пользователей — некого назначить ответственным.")

    b2c_clients = list(B2CClient.objects.filter(is_active=True))
    b2c_count = round(count * B2C_RATIO) if b2c_clients else 0
    university_count = count - b2c_count

    existing = Interaction.objects.filter(comment__startswith=SEED_COMMENT_PREFIX).count()
    created = [
        _build_interaction(
            number=number,
            universities=universities,
            b2c_clients=b2c_clients,
            university_count=university_count,
        )
        for number in range(existing, count)
    ]
    Interaction.objects.bulk_create(created)
    Responsible.objects.bulk_create(
        [Responsible(interaction=interaction, manager=manager) for interaction in created],
    )

    return SeedResult(
        created=len(created),
        with_universities=sum(interaction.university_id is not None for interaction in created),
        with_b2c_clients=sum(interaction.b2c_client_id is not None for interaction in created),
        existing=existing,
        manager=manager,
    )


def _resolve_manager(manager_email: str) -> AbstractBaseUser | None:
    """Ответственный для тестовых взаимодействий: КАМ по почте, иначе любой активный пользователь."""
    user_model = get_user_model()
    return (
        user_model.objects.filter(email__iexact=manager_email, is_active=True).first()
        or user_model.objects.filter(is_active=True).first()
    )


def _build_interaction(
    number: int,
    universities: list[University],
    b2c_clients: list[B2CClient],
    university_count: int,
) -> Interaction:
    """Собирает взаимодействие с контрагентом по порядковому номеру: сначала вузы, потом B2C-клиенты."""
    if number < university_count:
        university = universities[number % len(universities)]
        return Interaction(
            comment=f"{SEED_COMMENT_PREFIX} Взаимодействие с вузом #{number + 1}",
            university=university,
        )

    b2c_client = b2c_clients[(number - university_count) % len(b2c_clients)]
    return Interaction(
        comment=f"{SEED_COMMENT_PREFIX} Взаимодействие с B2C-клиентом #{number + 1}",
        b2c_client=b2c_client,
    )
