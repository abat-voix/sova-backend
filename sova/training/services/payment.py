import uuid

from django.db import transaction

from sova.core.crypto import blind_index
from sova.core.text import email_key, phone_key, text_key
from sova.training.enum import TrainingApplicationStatus
from sova.training.exceptions import TrainingError
from sova.training.models import Learner, TrainingApplicationLearner, TrainingStream
from sova.training.services.application import training_application_service


class TrainingPaymentService:
    """
    Регистрация оплаты из внешних данных (JSON оплат, интеграция): по потоку, программе, ФИО и контактам (все заполненные с обеих сторон должны совпасть) находится
    участник заявки потока и получает `is_paid=True`. Обучающийся без заявки на поток оплату не получает.
    """

    @staticmethod
    def find_stream(stream_id) -> TrainingStream:
        """Поток по его id (UUID); номер потока в данных — это id."""
        try:
            pk = uuid.UUID(str(stream_id).strip())
        except ValueError:
            pk = None
        stream = TrainingStream.objects.select_related("interaction_program__program").filter(pk=pk).first()
        if stream is None:
            raise TrainingError("stream_not_found", f"Поток не найден: {stream_id}.")
        return stream

    @staticmethod
    def check_course(stream: TrainingStream, course: str) -> None:
        """Курс из данных должен совпадать с программой потока."""
        program = stream.interaction_program.program
        if text_key(course) != text_key(program.name):
            raise TrainingError(
                "course_mismatch",
                f"Курс «{course}» не совпадает с программой потока «{program.name}».",
            )

    @staticmethod
    def _matches(learner: Learner, full_name: tuple[str, str, str], email_hash: str, phone_hash: str) -> bool:
        """
        ФИО совпадает, и каждый контакт, заполненный и в данных, и у обучающегося, совпадает; хотя бы один контакт
        должен совпасть. Контакт, пустой с одной из сторон, не сравнивается.
        """
        learner_name = tuple(text_key(part) for part in (learner.last_name, learner.first_name, learner.middle_name))
        if learner_name != full_name:
            return False
        compared = [
            expected == actual
            for expected, actual in ((email_hash, learner.email_hash), (phone_hash, learner.phone_hash))
            if expected and actual
        ]
        return bool(compared) and all(compared)

    def find_participant(
        self,
        *,
        stream_id,
        course: str,
        last_name: str,
        first_name: str,
        middle_name: str = "",
        email: str = "",
        phone: str = "",
    ) -> TrainingApplicationLearner:
        """Участник действующей заявки потока, однозначно определённый по ФИО и email/телефону."""
        stream = self.find_stream(stream_id)
        self.check_course(stream, course)
        email_hash = blind_index(email_key(email))
        phone_hash = blind_index(phone_key(phone or ""))
        if not email_hash and not phone_hash:
            raise TrainingError("learner_contacts_missing", "Нужен email или телефон обучающегося.")
        full_name = tuple(text_key(part or "") for part in (last_name, first_name, middle_name))
        participants = [
            participant
            for participant in TrainingApplicationLearner.objects.select_related("learner").filter(
                application__stream=stream,
                application__status=TrainingApplicationStatus.NEW,
            )
            if self._matches(participant.learner, full_name, email_hash, phone_hash)
        ]
        if len(participants) > 1:
            raise TrainingError("learner_ambiguous", "Обучающийся определён неоднозначно: подходит несколько участников.")
        if participants:
            return participants[0]
        learner_exists = any(
            self._matches(learner, full_name, email_hash, phone_hash)
            for learner in Learner.objects.filter(is_active=True)
            .exclude(email_hash="", phone_hash="")
            .filter(last_name__iexact=last_name.strip())
        )
        if learner_exists:
            raise TrainingError("learner_not_in_stream", "Обучающийся найден, но не привязан к заявке этого потока.")
        raise TrainingError("learner_not_found", "Обучающийся не найден.")

    @staticmethod
    def mark_paid(participant: TrainingApplicationLearner) -> TrainingApplicationLearner:
        """Ставит участнику факт оплаты; повторная отметка ничего не меняет."""
        if participant.is_paid:
            return participant
        return training_application_service.set_paid(participant, True)

    @transaction.atomic
    def register(self, **data) -> TrainingApplicationLearner:
        """Находит участника по данным оплаты (см. `find_participant`) и отмечает оплату."""
        return self.mark_paid(self.find_participant(**data))


training_payment_service = TrainingPaymentService()
