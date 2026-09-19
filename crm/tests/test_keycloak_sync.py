from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone

from crm.models import UserProfile
from crm.services.keycloak_sync import sync_user_from_claims

_SUB = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


class SyncUserFromClaimsTestCase(TestCase):
    """Тесты crm.services.keycloak_sync.sync_user_from_claims."""

    def setUp(self) -> None:
        """
        Подготовка данных перед каждым тестом.

        get_or_create, а не create: миграция 0002_seed_role_groups уже заводит
        эти группы в тестовой БД.
        """
        self.manager_group, _ = Group.objects.get_or_create(name="Руководитель")
        self.admin_group, _ = Group.objects.get_or_create(name="Администратор")

    def test_creates_new_user_with_unusable_password(self) -> None:
        """Первый вызов заводит User + UserProfile, пароль недоступен (identity только через Keycloak)."""
        user = sync_user_from_claims(
            {"sub": _SUB, "preferred_username": "petrov", "email": "petrov@example.com", "given_name": "Пётр"},
        )

        self.assertEqual(user.email, "petrov@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(UserProfile.objects.filter(user=user, keycloak_id=_SUB).exists())

    def test_second_call_updates_same_user_not_creates_new(self) -> None:
        """Повторный вызов с тем же sub обновляет тот же User, а не создаёт нового."""
        first = sync_user_from_claims({"sub": _SUB, "email": "old@example.com"})
        second = sync_user_from_claims({"sub": _SUB, "email": "new@example.com"})

        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.email, "new@example.com")

    def test_syncs_groups_from_realm_roles(self) -> None:
        """Роли из claims становятся группами пользователя."""
        user = sync_user_from_claims({"sub": _SUB, "realm_access": {"roles": ["Руководитель", "Администратор"]}})

        self.assertEqual(set(user.groups.values_list("name", flat=True)), {"Руководитель", "Администратор"})

    def test_revokes_groups_no_longer_present(self) -> None:
        """Роль, снятая в Keycloak, снимается и с пользователя при следующей синхронизации."""
        user = sync_user_from_claims({"sub": _SUB, "realm_access": {"roles": ["Руководитель"]}})
        self.assertTrue(user.groups.filter(name="Руководитель").exists())

        sync_user_from_claims({"sub": _SUB, "realm_access": {"roles": []}})
        user.refresh_from_db()

        self.assertFalse(user.groups.filter(name="Руководитель").exists())

    def test_unknown_role_auto_creates_empty_group(self) -> None:
        """
        Роль из Keycloak, для которой в CRM ещё нет Group, создаётся автоматически — без прав.

        Раньше (filter(name__in=...)) такая роль тихо игнорировалась, что противоречило
        цели "новая роль в Keycloak сама появляется в системе, права на неё раздаёт админ".
        """
        user = sync_user_from_claims({"sub": _SUB, "realm_access": {"roles": ["Новая роль из Keycloak"]}})

        group = Group.objects.get(name="Новая роль из Keycloak")
        self.assertTrue(user.groups.filter(pk=group.pk).exists())
        self.assertEqual(group.permissions.count(), 0)

    def test_skips_role_sync_when_token_not_newer_than_last_sync(self) -> None:
        """Повторный вызов с тем же (или более старым) iat не переписывает роли — экономим запись в БД."""
        now = timezone.now()
        iat = int(now.timestamp())

        user = sync_user_from_claims({"sub": _SUB, "iat": iat, "realm_access": {"roles": ["Руководитель"]}})
        self.assertTrue(user.groups.filter(name="Руководитель").exists())

        # Роль сняли в Keycloak, но токен формально тот же (iat не новее) — синхронизация не должна сработать.
        sync_user_from_claims({"sub": _SUB, "iat": iat, "realm_access": {"roles": []}})
        user.refresh_from_db()

        self.assertTrue(user.groups.filter(name="Руководитель").exists())

    def test_resyncs_when_token_is_newer(self) -> None:
        """Более новый iat (например, после refresh токена) запускает реальную синхронизацию ролей."""
        first_iat = int(timezone.now().timestamp())
        user = sync_user_from_claims({"sub": _SUB, "iat": first_iat, "realm_access": {"roles": ["Руководитель"]}})
        self.assertTrue(user.groups.filter(name="Руководитель").exists())

        second_iat = first_iat + 600  # новый access-токен, выпущенный позже
        sync_user_from_claims({"sub": _SUB, "iat": second_iat, "realm_access": {"roles": []}})
        user.refresh_from_db()

        self.assertFalse(user.groups.filter(name="Руководитель").exists())

    def test_first_login_syncs_roles_even_though_profile_is_just_created(self) -> None:
        """
        Регрессионный тест на баг из черновика: сравнение last_synced_at с iat не должно

        приводить к пропуску роли на самом первом логине — last_synced_at профиля
        обновляется только внутри самой синхронизации, а не как побочный эффект create().
        """
        old_iat = int((timezone.now() - timedelta(hours=1)).timestamp())

        user = sync_user_from_claims({"sub": _SUB, "iat": old_iat, "realm_access": {"roles": ["Руководитель"]}})

        self.assertTrue(user.groups.filter(name="Руководитель").exists())
