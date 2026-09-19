from datetime import datetime
from datetime import timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from crm.models import UserProfile

User = get_user_model()


def sync_user_from_claims(claims: dict) -> "User":
    """
    Get-or-create пользователя Django и его UserProfile по claims Keycloak-токена.

    Роли синхронизируются в user.groups через .set() — оно само добавляет новые
    группы и убирает те, что сняли в Keycloak, за один вызов. Новая realm role,
    для которой ещё нет Group, создаётся автоматически (без единого Permission —
    их раздаёт администратор через /admin/auth/group/). Без этого роль, заведённая
    в Keycloak, тихо игнорировалась бы вместо появления в системе.

    Синхронизация ролей (запись в M2M) пропускается, если claims["iat"] не новее
    profile.last_synced_at — тот же access-токен, что и на прошлый запрос, не должен
    порождать DELETE+INSERT в user_groups на каждый HTTP-запрос. last_synced_at
    обновляется ТОЛЬКО в момент реальной синхронизации ролей, а не при обновлении
    email/имени — иначе (например, если проставлять его при любом save() профиля)
    самый первый логин может ошибочно решить, что уже "всё синхронизировано", и
    пропустить единственный шанс проставить роли новому пользователю.

    Не используем User.objects.update_or_create(profile__keycloak_id=...) — dunder-путь
    через связанную модель не работает в create-ветке update_or_create (Django пытается
    передать "profile__keycloak_id" как есть в конструктор User, а это не поле модели).
    Поэтому ищем через UserProfile и обновляем/создаём User отдельным шагом.
    """
    keycloak_id = claims["sub"]
    token_issued_at = _parse_iat(claims)

    profile = UserProfile.objects.filter(keycloak_id=keycloak_id).select_related("user").first()

    user_fields = {
        "email": claims.get("email", ""),
        "first_name": claims.get("given_name", ""),
        "last_name": claims.get("family_name", ""),
        "is_active": True,
    }

    if profile is not None:
        user = profile.user
        if token_issued_at is not None and profile.last_synced_at >= token_issued_at:
            # Тот же (или более старый) токен, что и на прошлой синхронизации — не пишем в БД.
            return user
        User.objects.filter(pk=user.pk).update(**user_fields)
        user.refresh_from_db()
    else:
        user = User(username=claims.get("preferred_username") or keycloak_id, **user_fields)
        user.set_unusable_password()
        user.save()
        profile = UserProfile.objects.create(user=user, keycloak_id=keycloak_id)

    role_names = claims.get("realm_access", {}).get("roles", [])
    groups = [Group.objects.get_or_create(name=name)[0] for name in role_names]
    user.groups.set(groups)

    profile.last_synced_at = timezone.now()
    profile.save(update_fields=["last_synced_at"])

    return user


def _parse_iat(claims: dict) -> datetime | None:
    """Момент выпуска токена (claims['iat']) как aware datetime, либо None, если отсутствует."""
    iat = claims.get("iat")
    if iat is None:
        return None
    return datetime.fromtimestamp(iat, tz=dt_timezone.utc)
