from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from sova.core.models import UUIDModel
from sova.notifications.enum import (
    DEADLINE_NOTIFY_TYPES,
    DeliveryMode,
    HeadMode,
    NotificationChannel,
    NotifyEvent,
    NotifyType,
)


class NotifySettings(UUIDModel):
    """
    Настройки одного типа уведомления: включено, кому, по каким каналам; для типов сроков — ещё расписание.

    Строк ровно по одной на NotifyType, их создаёт data-миграция. Для сроков ответственный — исполнитель действия
    или активный КАМ взаимодействия, руководитель — по head_mode; для событийных типов обоих передаёт код события.
    """

    notify_type = models.CharField(
        max_length=20,
        choices=NotifyType.choices,
        unique=True,
        verbose_name="Тип уведомления",
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name="Включено",
    )
    is_notify_responsible = models.BooleanField(
        default=True,
        verbose_name="Ответственному",
    )
    is_notify_head = models.BooleanField(
        default=False,
        verbose_name="Руководителю",
    )
    head_mode = models.CharField(
        max_length=20,
        choices=HeadMode.choices,
        default=HeadMode.ASSIGNED_BY,
        verbose_name="Руководитель",
        help_text=(
            "«Назначивший руководитель» — тот, кто назначил КАМа на взаимодействие, если у него роль "
            "«Руководитель»; иначе — все руководители. Только для сроков: в событийных уведомлениях руководителя "
            "передаёт код события."
        ),
    )
    is_fallback_to_head = models.BooleanField(
        default=True,
        verbose_name="Нет ответственного — руководителю",
        help_text="Только для сроков: если получатель «ответственный» выбран, но ответственного нет.",
    )
    remind_before_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Предупреждать за, дней",
        help_text="Только для сроков. Пусто — не предупреждать.",
    )
    is_remind_responsible = models.BooleanField(
        default=True,
        verbose_name="Предупреждение — ответственному",
        help_text="Только для сроков.",
    )
    is_remind_head = models.BooleanField(
        default=False,
        verbose_name="Предупреждение — руководителю",
        help_text="Только для сроков.",
    )
    is_channel_email = models.BooleanField(
        default=True,
        verbose_name="Email",
    )
    is_channel_telegram = models.BooleanField(
        default=True,
        verbose_name="Telegram",
    )
    is_channel_max = models.BooleanField(
        default=True,
        verbose_name="MAX",
    )
    is_channel_system = models.BooleanField(
        default=True,
        verbose_name="В системе",
    )
    delivery_mode = models.CharField(
        max_length=20,
        choices=DeliveryMode.choices,
        default=DeliveryMode.DIGEST,
        verbose_name="Доставка",
        help_text="Только для сроков.",
    )
    repeat_every_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Повторять о просрочке раз в, дней",
        help_text="Только для сроков. Пусто — сообщить один раз.",
    )
    is_skip_weekends = models.BooleanField(
        default=False,
        verbose_name="Не отправлять в выходные",
        help_text="Только для сроков.",
    )

    class Meta:
        verbose_name = "Настройки уведомления"
        verbose_name_plural = "Настройки уведомлений"
        ordering = ["notify_type"]

    def __str__(self):
        return self.get_notify_type_display()

    def clean(self) -> None:
        """Расписание — только у типов сроков; у включённого типа — хотя бы один канал и получатель."""
        errors: dict[str, str] = {}
        is_deadline = self.notify_type in DEADLINE_NOTIFY_TYPES
        if not is_deadline:
            for field in ("remind_before_days", "repeat_every_days"):
                if getattr(self, field) is not None:
                    errors[field] = "Только для уведомлений о сроках."
        if self.is_enabled:
            if not self.channels():
                errors["is_channel_system"] = "Выберите хотя бы один канал."
            if not (self.is_notify_responsible or self.is_notify_head):
                errors["is_notify_responsible"] = "Выберите хотя бы одного получателя."
            if (
                is_deadline
                and self.remind_before_days is not None
                and not (self.is_remind_responsible or self.is_remind_head)
            ):
                errors["is_remind_responsible"] = "Выберите хотя бы одного получателя предупреждения."
        if errors:
            raise ValidationError(errors)

    def channels(self) -> list[NotificationChannel]:
        """Включённые каналы доставки."""
        flags = (
            (NotificationChannel.EMAIL, self.is_channel_email),
            (NotificationChannel.TELEGRAM, self.is_channel_telegram),
            (NotificationChannel.MAX, self.is_channel_max),
            (NotificationChannel.SYSTEM, self.is_channel_system),
        )
        return [channel for channel, is_on in flags if is_on]

    def recipient_flags(self, event: str) -> tuple[bool, bool]:
        """Флаги «ответственному» и «руководителю» для события сроков."""
        if event == NotifyEvent.REMINDER:
            return self.is_remind_responsible, self.is_remind_head
        return self.is_notify_responsible, self.is_notify_head
