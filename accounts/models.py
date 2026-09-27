from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SystemRole(models.TextChoices):
    """Прикладные роли пользователя в СОВА. Права ролей — `accounts.policy`."""

    OBSERVER = "observer", "Наблюдатель"
    KAM = "kam", "КАМ"
    HEAD = "head", "Руководитель"
    PLATFORM_ADMIN = "platform_admin", "Администратор платформы"


class UserRole(models.Model):
    """Единственная прикладная роль пользователя в СОВА."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="system_role",
        verbose_name="Пользователь",
    )
    role = models.CharField(
        max_length=32,
        choices=SystemRole.choices,
        verbose_name="Роль в системе",
    )

    class Meta:
        verbose_name = "роль пользователя"
        verbose_name_plural = "роли пользователей"

    def __str__(self) -> str:
        return f"{self.user} — {self.get_role_display()}"


class Supervision(models.Model):
    """
    Подчинение КАМа руководителю.

    У КАМа не больше одного руководителя, у руководителя — сколько угодно КАМов. Связь создаётся и удаляется только
    через `account_service`: при смене роли или деактивации участника она удаляется, а участники получают уведомления.
    Код, читающий связь, всё равно проверяет текущие роль и активность: запись, изменённую в обход сервиса
    (shell, `loaddata`, миграции), он просто не учитывает.
    """

    kam = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supervision",
        verbose_name="КАМ",
    )
    head = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supervised",
        verbose_name="Руководитель",
    )

    class Meta:
        verbose_name = "руководитель КАМа"
        verbose_name_plural = "руководители КАМов"

    def __str__(self) -> str:
        return f"{self.kam} → {self.head}"

    def clean(self) -> None:
        """Связывать можно только активного КАМа с активным руководителем."""
        # Роли разные, поэтому пользователь не может оказаться руководителем самому себе
        errors = {}
        if self.kam_id and not self._has_active_role(user=self.kam, role=SystemRole.KAM):
            errors["kam"] = "Подчинённым может быть только активный пользователь с ролью «КАМ»."
        if self.head_id and not self._has_active_role(user=self.head, role=SystemRole.HEAD):
            errors["head"] = "Руководителем может быть только активный пользователь с ролью «Руководитель»."
        if errors:
            raise ValidationError(errors)

    @staticmethod
    def _has_active_role(user, role: str) -> bool:
        """Активен ли пользователь и совпадает ли его роль с `role`."""
        assignment = getattr(user, "system_role", None)
        return user.is_active and assignment is not None and assignment.role == role
