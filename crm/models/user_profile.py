from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """
    Связка пользователя Django с его идентификатором в Keycloak.
    """

    keycloak_id = models.UUIDField(
        unique=True,
        db_index=True,
        verbose_name="Идентификатор в Keycloak",
    )
    last_synced_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Последняя синхронизация",
    )

    user = models.OneToOneField(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Пользователь",
    )

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self):
        return str(self.user)
