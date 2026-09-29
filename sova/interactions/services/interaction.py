from django.db import transaction
from django.db.models import BooleanField, Case, Exists, OuterRef, QuerySet, Value, When

from sova.interactions.exceptions import InteractionDeleteError
from sova.interactions.models import Contract, Interaction
from sova.processes.models import WorkflowInstance


class InteractionService:
    """
    Взаимодействие целиком. Удалить можно только незапущенное: пока по нему нет процесса.

    Процесс хранит историю работы (действия, результаты, вложения) — запущенное взаимодействие не удаляют.
    Договоры защищены на уровне БД (`on_delete=PROTECT`); здесь — понятная ошибка вместо общей.
    Вместе с взаимодействием удаляются состав, контакты, история ответственных и чат.
    """

    def annotate_can_delete(self, queryset: QuerySet[Interaction]) -> QuerySet[Interaction]:
        """Добавляет признак `can_delete` по тем же правилам, что `delete`, — без запроса на каждую строку."""
        started = Exists(WorkflowInstance.objects.filter(interaction=OuterRef("pk")))
        has_contracts = Exists(Contract.objects.filter(interaction=OuterRef("pk")))
        return queryset.annotate(
            can_delete=Case(
                When(started | has_contracts, then=Value(False)),
                default=Value(True),
                output_field=BooleanField(),
            ),
        )

    def can_delete(self, interaction: Interaction) -> bool:
        """Можно ли удалить взаимодействие."""
        return not interaction.workflow_instances.exists() and not interaction.contracts.exists()

    @transaction.atomic
    def delete(self, interaction: Interaction) -> None:
        """
        Удаляет незапущенное взаимодействие.

        Блокировка строки взаимодействия та же, что при запуске процесса (`WorkflowEngineService.start`):
        запуск и удаление не проходят одновременно.
        """
        Interaction.objects.select_for_update().get(pk=interaction.pk)
        if interaction.workflow_instances.exists():
            raise InteractionDeleteError(
                detail="По взаимодействию уже запущен процесс — удалить его нельзя.",
                code="workflow_started",
            )
        if interaction.contracts.exists():
            raise InteractionDeleteError(
                detail="К взаимодействию привязаны договоры — удалить его нельзя.",
                code="has_contracts",
            )
        interaction.delete()


interaction_service = InteractionService()
