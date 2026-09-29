from django.db import transaction
from django.db.models import QuerySet

from sova.interactions.models import Contract, InteractionProgram
from sova.training.enum import TrainingStreamStatus
from sova.training.exceptions import TrainingError
from sova.training.models import TrainingInstructor, TrainingStream, TrainingStreamInstructor


CLOSED_STREAM_STATUSES = (TrainingStreamStatus.COMPLETED, TrainingStreamStatus.CANCELLED)


class TrainingStreamService:
    """Потоки обучения и назначение преподавателей — единая точка проверок для API и ActionFeature."""

    @transaction.atomic
    def create_training_stream(
        self,
        interaction_program: InteractionProgram,
        name: str,
        user,
        instructors=(),
        **fields,
    ) -> TrainingStream:
        """
        Создаёт поток по программе взаимодействия.

        Программа должна быть активной, а у взаимодействия — подписанный договор: поток запускают после заключения
        договора. Обучение возможно и с организацией, и с B2C-клиентом.
        """
        self.check_can_create(interaction_program)
        stream = TrainingStream.objects.create(
            interaction_program=interaction_program,
            name=name,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            **fields,
        )
        for instructor in instructors:
            self.assign_instructor(stream=stream, instructor=instructor, user=user)
        return stream

    @staticmethod
    def check_can_create(interaction_program: InteractionProgram) -> None:
        """Проверяет условия создания потока по программе."""
        if interaction_program.interaction_id is None:
            raise TrainingError("program_without_interaction", "Программа не относится к взаимодействию.")
        if not interaction_program.is_active:
            raise TrainingError("program_inactive", "Программа взаимодействия неактивна.")
        has_signed_contract = Contract.objects.filter(
            interaction_id=interaction_program.interaction_id,
            signed_at__isnull=False,
        ).exists()
        if not has_signed_contract:
            raise TrainingError("contract_not_signed", "У взаимодействия нет подписанного договора.")

    @staticmethod
    def suitable_instructors(interaction_program: InteractionProgram, queryset: QuerySet | None = None) -> QuerySet:
        """Кто может вести поток по программе: активные, из контрагента, программа есть у них."""
        interaction = interaction_program.interaction
        queryset = TrainingInstructor.objects.all() if queryset is None else queryset
        return queryset.filter(
            organization_id=interaction.organization_id,
            b2c_client_id=interaction.b2c_client_id,
            programs=interaction_program.program_id,
            is_active=True,
        )

    def assignable_instructors(self, stream: TrainingStream, queryset: QuerySet | None = None) -> QuerySet:
        """Кого ещё можно назначить на поток: подходящие по программе и не назначенные; на закрытый поток — никого."""
        if stream.status in CLOSED_STREAM_STATUSES:
            return TrainingInstructor.objects.none()
        return self.suitable_instructors(stream.interaction_program, queryset).exclude(stream_links__stream=stream)

    @staticmethod
    def check_stream_open(stream: TrainingStream) -> None:
        """Состав преподавателей завершённого или отменённого потока не меняют."""
        if stream.status in CLOSED_STREAM_STATUSES:
            raise TrainingError("stream_closed", "Поток завершён или отменён.")

    def assign_instructor(
        self,
        stream: TrainingStream,
        instructor: TrainingInstructor,
        user,
    ) -> TrainingStreamInstructor:
        """
        Назначает преподавателя на открытый поток.

        Преподаватель активен, работает в организации-контрагенте взаимодействия потока и ведёт программу потока.
        """
        self.check_stream_open(stream)
        interaction_program = stream.interaction_program
        interaction = interaction_program.interaction
        if not instructor.is_active:
            raise TrainingError("instructor_inactive", "Преподаватель неактивен.")
        same_organization = (
            instructor.organization_id == interaction.organization_id
            and instructor.b2c_client_id == interaction.b2c_client_id
        )
        if not same_organization:
            raise TrainingError(
                "instructor_counterparty_mismatch",
                "Преподаватель работает не в организации-контрагенте взаимодействия.",
            )
        if not instructor.programs.filter(pk=interaction_program.program_id).exists():
            raise TrainingError("instructor_program_mismatch", "Преподаватель не ведёт программу потока.")
        if stream.instructor_links.filter(instructor=instructor).exists():
            raise TrainingError("instructor_already_assigned", "Преподаватель уже назначен на поток.")
        return TrainingStreamInstructor.objects.create(
            stream=stream,
            instructor=instructor,
            assigned_by=user if getattr(user, "is_authenticated", False) else None,
        )

    def unassign_instructor(self, stream: TrainingStream, instructor: TrainingInstructor) -> None:
        """Снимает преподавателя с открытого потока."""
        self.check_stream_open(stream)
        stream.instructor_links.filter(instructor=instructor).delete()


training_stream_service = TrainingStreamService()
