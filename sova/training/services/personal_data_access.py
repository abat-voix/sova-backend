from accounts.policy import Action, can
from sova.training.enum import PersonalDataAccessAction
from sova.training.models import Learner, LearnerPersonalData, LearnerPersonalDataAccessLog


class PersonalDataAccessService:
    """
    Доступ к полным персональным данным обучающихся: только по праву `training.personal_data.read`
    (администратор платформы), каждая выдача расшифрованных данных пишется в журнал (приказ ФСТЭК № 117).
    """

    # Поля, которые выдаются только по праву на персональные данные
    FIELDS = tuple(
        field.name
        for field in LearnerPersonalData._meta.concrete_fields
        if field.name not in {"id", "learner", "snils_hash", "created_at", "updated_at"}
    )

    @staticmethod
    def can_read(user) -> bool:
        """Может ли пользователь видеть полные персональные данные обучающихся."""
        return can(user, Action.TRAINING_PERSONAL_DATA_READ)

    def log_access(
        self,
        user,
        learner: Learner,
        fields=None,
        action: str = PersonalDataAccessAction.READ,
        request=None,
    ) -> LearnerPersonalDataAccessLog:
        """Записывает выдачу расшифрованных персональных данных в журнал."""
        return LearnerPersonalDataAccessLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            learner=learner,
            fields=list(self.FIELDS if fields is None else fields),
            action=action,
            ip=(request.META.get("REMOTE_ADDR") or None) if request is not None else None,
        )


personal_data_access_service = PersonalDataAccessService()
