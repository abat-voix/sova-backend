from django.db import transaction

from sova.training.enum import TrainingApplicationStatus, TrainingStreamStatus
from sova.training.exceptions import TrainingError
from sova.training.models import Learner, TrainingApplication, TrainingApplicationLearner, TrainingStream


class TrainingApplicationService:
    """Заявки на потоки: создание, состав участников, факт оплаты участника, отмена и удаление."""

    @transaction.atomic
    def create_application(
        self,
        stream: TrainingStream,
        user,
        learners=(),
        comment: str = "",
    ) -> TrainingApplication:
        """Создаёт заявку на поток вместе с участниками."""
        self.check_stream_open(stream)
        application = TrainingApplication.objects.create(
            stream=stream,
            comment=comment,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        for learner in learners:
            self.add_learner(application=application, learner=learner)
        return application

    @staticmethod
    def check_stream_open(stream: TrainingStream) -> None:
        """В отменённый поток заявки не принимаются."""
        if stream.status == TrainingStreamStatus.CANCELLED:
            raise TrainingError("stream_cancelled", "Поток отменён.")

    @staticmethod
    def add_learner(
        application: TrainingApplication,
        learner: Learner,
        is_paid: bool = False,
    ) -> TrainingApplicationLearner:
        """Добавляет обучающегося в заявку (сразу с фактом оплаты, если он известен); один человек — один раз."""
        if application.status == TrainingApplicationStatus.CANCELLED:
            raise TrainingError("application_cancelled", "Заявка отменена.")
        if application.participants.filter(learner=learner).exists():
            raise TrainingError("learner_already_in_application", "Обучающийся уже есть в заявке.")
        return TrainingApplicationLearner.objects.create(application=application, learner=learner, is_paid=is_paid)

    def remove_learner(self, application: TrainingApplication, learner: Learner) -> None:
        """Убирает обучающегося из заявки; оплатившего — не убирает."""
        participant = application.participants.filter(learner=learner).first()
        if participant is not None:
            self.delete_participant(participant)

    @staticmethod
    def delete_participant(participant: TrainingApplicationLearner) -> None:
        """Удаляет участника заявки; оплатившего не удаляют — сначала снимают отметку об оплате."""
        if participant.is_paid:
            raise TrainingError("learner_paid", "Обучающийся оплатил — сначала снимите отметку об оплате.")
        participant.delete()

    @staticmethod
    def set_paid(participant: TrainingApplicationLearner, is_paid: bool) -> TrainingApplicationLearner:
        """Ставит или снимает факт оплаты участника заявки."""
        participant.is_paid = is_paid
        participant.save(update_fields=["is_paid", "updated_at"])
        return participant

    @staticmethod
    @transaction.atomic
    def delete_application(application: TrainingApplication) -> None:
        """Удаляет заявку без оплативших участников; заявку с оплатой только отменяют."""
        if application.participants.filter(is_paid=True).exists():
            raise TrainingError("application_has_paid_learners", "В заявке есть оплатившие участники — её нельзя удалить.")
        application.delete()

    @staticmethod
    def cancel(application: TrainingApplication) -> TrainingApplication:
        """Отменяет заявку: её участники перестают считаться зачисленными."""
        application.status = TrainingApplicationStatus.CANCELLED
        application.save(update_fields=["status", "updated_at"])
        return application


training_application_service = TrainingApplicationService()
