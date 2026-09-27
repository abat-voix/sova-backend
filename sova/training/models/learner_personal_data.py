from django.db import models

from sova.core.crypto import blind_index
from sova.core.fields import EncryptedDateField, EncryptedTextField
from sova.core.models import TimeStampedModel
from sova.core.text import snils_key
from sova.training.enum import EducationLevel, Gender


class LearnerPersonalData(TimeStampedModel):
    """
    Персональные данные обучающегося из файла загрузки: документы, адрес, образование.

    Полностью видны только администратору платформы, каждый просмотр пишется в `LearnerPersonalDataAccessLog`.
    Всё зашифровано, кроме пола, уровня образования и ФИО в дательном падеже.
    """

    learner = models.OneToOneField(
        to="training.Learner",
        on_delete=models.CASCADE,
        related_name="personal_data",
        verbose_name="Обучающийся",
    )
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True, verbose_name="Пол")
    birth_date = EncryptedDateField(null=True, blank=True, verbose_name="Дата рождения")
    last_name_dative = models.CharField(max_length=255, blank=True, verbose_name="Фамилия (дательный падеж)")
    first_name_dative = models.CharField(max_length=255, blank=True, verbose_name="Имя (дательный падеж)")
    middle_name_dative = models.CharField(max_length=255, blank=True, verbose_name="Отчество (дательный падеж)")

    snils = EncryptedTextField(blank=True, verbose_name="СНИЛС")
    snils_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)

    passport_series = EncryptedTextField(blank=True, verbose_name="Серия паспорта")
    passport_number = EncryptedTextField(blank=True, verbose_name="Номер паспорта")
    passport_issued_by = EncryptedTextField(blank=True, verbose_name="Кем выдан паспорт")
    passport_issued_at = EncryptedDateField(null=True, blank=True, verbose_name="Дата выдачи паспорта")
    passport_division_code = EncryptedTextField(blank=True, verbose_name="Код подразделения")

    registration_region = EncryptedTextField(blank=True, verbose_name="Регион регистрации")
    registration_locality = EncryptedTextField(blank=True, verbose_name="Населённый пункт регистрации")
    registration_street = EncryptedTextField(blank=True, verbose_name="Улица регистрации")
    registration_house = EncryptedTextField(blank=True, verbose_name="Дом регистрации")
    registration_apartment = EncryptedTextField(blank=True, verbose_name="Квартира регистрации")
    registration_postcode = EncryptedTextField(blank=True, verbose_name="Индекс регистрации")

    education_level = models.CharField(
        max_length=30,
        choices=EducationLevel.choices,
        blank=True,
        verbose_name="Образование",
    )
    diploma_qualification = EncryptedTextField(blank=True, verbose_name="Профессия по диплому")
    diploma_institution = EncryptedTextField(blank=True, verbose_name="Учебное заведение по диплому")
    diploma_last_name = EncryptedTextField(blank=True, verbose_name="Фамилия, указанная в дипломе")
    diploma_series = EncryptedTextField(blank=True, verbose_name="Серия диплома")
    diploma_number = EncryptedTextField(blank=True, verbose_name="Номер диплома")
    diploma_registration_number = EncryptedTextField(blank=True, verbose_name="Регистрационный номер диплома")
    diploma_issued_at = EncryptedDateField(null=True, blank=True, verbose_name="Дата выдачи диплома")

    class Meta:
        verbose_name = "Персональные данные обучающегося"
        verbose_name_plural = "Персональные данные обучающихся"

    def __str__(self):
        return f"Персональные данные: {self.learner}"

    def save(self, *args, **kwargs):
        self.snils_hash = blind_index(snils_key(self.snils))
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "snils_hash"}
        super().save(*args, **kwargs)
