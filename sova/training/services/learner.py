from django.db import transaction

from sova.core.crypto import blind_index
from sova.core.text import email_key, phone_key
from sova.training.enum import PersonalDataAccessAction
from sova.training.exceptions import LearnerExistsError
from sova.training.models import Learner, LearnerPersonalData
from sova.training.services.personal_data_access import personal_data_access_service


class LearnerService:
    """
    Ручное создание и правка карточки обучающегося (импорт — `LearnerImportService`).

    Контакт — email или телефон — один на человека: совпадение с другой карточкой — `LearnerExistsError`.
    Тёзки по ФИО — разные люди. Удаления нет — карточку выключают (`is_active`).
    """

    @transaction.atomic
    def create(self, **fields) -> Learner:
        """Создаёт карточку; согласие на обработку ПД при ручном создании не требуется."""
        self.check_unique_contacts(email=fields.get("email", ""), phone=fields.get("phone", ""))
        return Learner.objects.create(**fields)

    @transaction.atomic
    def update(self, learner: Learner, **fields) -> Learner:
        """Меняет карточку; новый контакт не должен принадлежать другому обучающемуся."""
        self.check_unique_contacts(
            email=fields.get("email", learner.email),
            phone=fields.get("phone", learner.phone),
            exclude=learner,
        )
        for name, value in fields.items():
            setattr(learner, name, value)
        learner.save()
        return learner

    @transaction.atomic
    def update_personal_data(self, learner: Learner, data: dict, user, request=None) -> LearnerPersonalData:
        """Меняет ПД (создаёт запись, если её ещё нет); изменённые поля пишутся в журнал доступа."""
        personal_data, _created = LearnerPersonalData.objects.get_or_create(learner=learner)
        for name, value in data.items():
            setattr(personal_data, name, value)
        personal_data.save()
        personal_data_access_service.log_access(
            user=user,
            learner=learner,
            fields=sorted(data),
            action=PersonalDataAccessAction.UPDATE,
            request=request,
        )
        return personal_data

    @staticmethod
    def check_unique_contacts(email: str, phone: str, exclude: Learner | None = None) -> None:
        """Карточка с тем же email или телефоном (по HMAC-индексам) — `LearnerExistsError`."""
        lookups = (
            ("email_hash", blind_index(email_key(email or ""))),
            ("phone_hash", blind_index(phone_key(phone or ""))),
        )
        for field, value in lookups:
            if not value:
                continue
            duplicate = Learner.objects.filter(**{field: value}).exclude(pk=getattr(exclude, "pk", None)).first()
            if duplicate is not None:
                raise LearnerExistsError(duplicate)


learner_service = LearnerService()
