from django.db import transaction

from sova.interactions.models import Contract, InteractionProgram
from sova.training.exceptions import TrainingError
from sova.training.models import TrainingInstructor, TrainingStream, TrainingStreamInstructor


class TrainingStreamService:
    """Потоки обучения и назначение преподавателей — единая точка проверок для API, ActionFeature и admin."""

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

    def assign_instructor(self, stream: TrainingStream, instructor: TrainingInstructor, user) -> TrainingStreamInstructor:
        """Назначает преподавателя: он активен и работает в организации-контрагенте взаимодействия потока."""
        interaction = stream.interaction_program.interaction
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
        if stream.instructor_links.filter(instructor=instructor).exists():
            raise TrainingError("instructor_already_assigned", "Преподаватель уже назначен на поток.")
        return TrainingStreamInstructor.objects.create(
            stream=stream,
            instructor=instructor,
            assigned_by=user if getattr(user, "is_authenticated", False) else None,
        )

    @staticmethod
    def unassign_instructor(stream: TrainingStream, instructor: TrainingInstructor) -> None:
        """Снимает преподавателя с потока."""
        stream.instructor_links.filter(instructor=instructor).delete()


training_stream_service = TrainingStreamService()
