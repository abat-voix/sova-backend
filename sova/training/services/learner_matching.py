from sova.core.crypto import blind_index
from sova.core.text import email_key, phone_key
from sova.training.exceptions import TrainingError
from sova.training.models import Learner


class LearnerMatchingService:
    """
    Поиск карточки обучающегося по контактам: сначала email, затем телефон (по HMAC-индексам).

    По одному ФИО карточки не объединяются: тёзки — разные люди. Найден по телефону, а email другой — тот же
    человек с предупреждением; email карточки при этом не перезаписывается.
    """

    def find(self, email: str, phone: str) -> tuple[Learner | None, list[str]]:
        """Карточка и предупреждения; несколько карточек с одним контактом — `learner_ambiguous`."""
        email = email_key(email)
        phone = phone_key(phone or "")
        if email:
            learner = self._single(email_hash=blind_index(email))
            if learner is not None:
                return learner, []
        if phone:
            learner = self._single(phone_hash=blind_index(phone))
            if learner is not None:
                warnings = []
                if email and learner.email and learner.email != email:
                    warnings.append(
                        f"обучающийся {learner} найден по телефону, email в файле другой — email карточки не изменён"
                    )
                return learner, warnings
        return None, []

    @staticmethod
    def _single(**lookup) -> Learner | None:
        found = list(Learner.objects.filter(**lookup)[:2])
        if len(found) > 1:
            raise TrainingError("learner_ambiguous", "Несколько обучающихся с такими контактами.")
        return found[0] if found else None


learner_matching_service = LearnerMatchingService()
