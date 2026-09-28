from django.db import models

from sova.core.crypto import blind_index
from sova.core.fields import EncryptedTextField
from sova.core.models import NormalizedTextFieldsMixin, TimeStampedModel
from sova.core.text import email_key, phone_key


class Learner(NormalizedTextFieldsMixin, TimeStampedModel):
    """
    Обучающийся — карточка человека, общая для всех его заявок; с вузом не связан.

    ФИО хранится открыто (поиск, списки). Email и телефон зашифрованы; для поиска и сопоставления рядом хранится
    HMAC-индекс нормализованного значения (`email_hash`, `phone_hash`). Карточки по одному ФИО не объединяются.
    """

    last_name = models.CharField(max_length=255, verbose_name="Фамилия")
    first_name = models.CharField(max_length=255, verbose_name="Имя")
    middle_name = models.CharField(max_length=255, blank=True, verbose_name="Отчество")
    email = EncryptedTextField(blank=True, verbose_name="Email")
    email_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    phone = EncryptedTextField(blank=True, verbose_name="Телефон")
    phone_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    consent_at = models.DateTimeField(null=True, blank=True, verbose_name="Согласие на обработку ПД")
    is_active = models.BooleanField(default=True, verbose_name="Активен")

    normalized_text_fields = ("last_name", "first_name", "middle_name")

    class Meta:
        verbose_name = "Обучающийся"
        verbose_name_plural = "Обучающиеся"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    def save(self, *args, **kwargs):
        self.email = email_key(self.email)
        self.phone = phone_key(self.phone or "")
        self.email_hash = blind_index(self.email)
        self.phone_hash = blind_index(self.phone)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "email_hash", "phone_hash"}
        super().save(*args, **kwargs)
