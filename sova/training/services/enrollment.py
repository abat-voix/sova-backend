from django.db.models import Exists, OuterRef, QuerySet

from sova.training.enum import TrainingApplicationStatus
from sova.training.models import TrainingApplicationLearner


class TrainingEnrollmentService:
    """
    Зачисление вычисляется, а не хранится: участник заявки зачислен, если он оплатил (`is_paid`), а заявка
    сопоставлена с потоком и действует. Оплата — только факт, без сумм и дат.
    """

    def enrolled_participants(
        self,
        queryset: QuerySet[TrainingApplicationLearner] | None = None,
    ) -> QuerySet[TrainingApplicationLearner]:
        """Зачисленные участники заявок."""
        queryset = TrainingApplicationLearner.objects.all() if queryset is None else queryset
        return queryset.filter(
            is_paid=True,
            application__stream__isnull=False,
            application__status=TrainingApplicationStatus.NEW,
        )

    def is_enrolled(self, participant: TrainingApplicationLearner) -> bool:
        """Зачислен ли участник заявки."""
        return self.enrolled_participants(TrainingApplicationLearner.objects.filter(pk=participant.pk)).exists()

    def with_enrollment(self, queryset: QuerySet[TrainingApplicationLearner]) -> QuerySet[TrainingApplicationLearner]:
        """Аннотирует участников признаком `is_enrolled` по тому же правилу, что `enrolled_participants`."""
        return queryset.annotate(is_enrolled=Exists(self.enrolled_participants().filter(pk=OuterRef("pk"))))


training_enrollment_service = TrainingEnrollmentService()
