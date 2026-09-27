from django.conf import settings
from django.db import models

from sova.core.models import UUIDModel
from sova.training.enum import PersonalDataAccessAction


class LearnerPersonalDataAccessLog(UUIDModel):
    """Журнал просмотров расшифрованных персональных данных (приказ ФСТЭК № 117)."""

    user = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        verbose_name="Пользователь",
    )
    learner = models.ForeignKey(
        to="training.Learner",
        on_delete=models.SET_NULL,
        related_name="personal_data_access_log",
        null=True,
        verbose_name="Обучающийся",
    )
    accessed_at = models.DateTimeField(auto_now_add=True, verbose_name="Когда")
    fields = models.JSONField(default=list, verbose_name="Поля")
    action = models.CharField(
        max_length=10,
        choices=PersonalDataAccessAction.choices,
        default=PersonalDataAccessAction.READ,
        verbose_name="Действие",
    )
    ip = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP-адрес")

    class Meta:
        verbose_name = "Доступ к персональным данным"
        verbose_name_plural = "Журнал доступа к персональным данным"
        ordering = ["-accessed_at"]

    def __str__(self):
        return f"{self.user} → {self.learner} ({self.accessed_at:%d.%m.%Y %H:%M})"
