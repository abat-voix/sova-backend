from django.db import models
from django.db.models.functions import Lower

from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel


class ContactPerson(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Контактное лицо — человек, без привязки к организации.

    С организациями его связывают `UniversityContact` / `B2CClientContact` / `VendorContact`: должность и способы
    связи принадлежат связи, а один человек может быть связан с несколькими организациями. ФИО не уникально —
    тёзки считаются разными людьми, пока пользователь явно не свяжет их или не сольёт.
    """

    full_name = models.CharField(
        max_length=255,
        verbose_name="ФИО",
    )
    email = models.EmailField(
        blank=True,
        verbose_name="Email",
    )
    phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Телефон",
    )
    telegram = models.CharField(
        max_length=64,
        blank=True,
        verbose_name="Telegram",
        help_text="Ник без @",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    normalized_text_fields = ("full_name", "phone", "telegram")

    class Meta:
        verbose_name = "Контактное лицо"
        verbose_name_plural = "Контактные лица"
        ordering = ["full_name"]
        # Поиск возможных дублей и сопоставление при импорте — без учёта регистра.
        indexes = [
            models.Index(Lower("full_name"), name="contact_person_full_name_ci"),
            models.Index(Lower("email"), name="contact_person_email_ci"),
            models.Index(Lower("telegram"), name="contact_person_telegram_ci"),
        ]

    def __str__(self):
        return self.full_name
