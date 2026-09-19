from django.conf import settings
from django.db import models


class SystemRole(models.TextChoices):
    """Прикладные роли пользователя в СОВА."""

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
