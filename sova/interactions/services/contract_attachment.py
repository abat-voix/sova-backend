from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from sova.interactions.exceptions import ContractAlreadyAttachedError
from sova.interactions.models import (
    Contract,
    Interaction,
    InteractionDirection,
    InteractionProduct,
    InteractionProgram,
)
from sova.interactions.services.responsible import responsible_service

_HEADLESS_MODELS = (InteractionDirection, InteractionProgram, InteractionProduct)


class ContractAttachmentService:
    """
    Переводит headless-договор (созданный импортом реестра) в состояние «привязан к Interaction».

    Не вызывает processes.services — запуск/досоздание этапов workflow остаётся на уровне
    API/оркестрации, как и для обычного создания Interaction (досоздание этапов в идущем
    процессе — `WorkflowEngineService.sync_contexts`).
    """

    @transaction.atomic
    def attach_to_new_interaction(
        self,
        contract: Contract,
        assigned_by: AbstractBaseUser | None,
        manager: AbstractBaseUser | None = None,
    ) -> Interaction:
        """
        Создаёт новый Interaction из headless-договора и переносит на него все его записи.

        Действующие ответственные договора (назначенные импортом реестра) становятся ответственными
        взаимодействия от имени `assigned_by`. `manager`, если передан, добавляется к ним; уже перешедший
        с договора менеджер не дублируется.
        """
        self._check_headless(contract=contract)
        interaction = Interaction.objects.create(
            university=contract.university,
            b2c_client=contract.b2c_client,
            comment=contract.draft_comment,
        )
        self._attach(contract=contract, interaction=interaction)
        responsible_service.transfer_from_contract(contract=contract, interaction=interaction, assigned_by=assigned_by)

        if manager is not None:
            responsible_service.assign(interaction=interaction, manager=manager, assigned_by=assigned_by)

        return interaction

    @transaction.atomic
    def attach_to_existing_interaction(self, contract: Contract, interaction: Interaction) -> None:
        """
        Привязывает дополнительный договор к уже существующему Interaction (переиздание/расширение).

        Ответственные договора не переносятся и остаются на договоре.
        """
        self._check_headless(contract=contract)
        self._attach(contract=contract, interaction=interaction)

    @staticmethod
    def _check_headless(contract: Contract) -> None:
        """Привязать можно только договор, ещё не привязанный к взаимодействию."""
        if contract.interaction_id is not None:
            raise ContractAlreadyAttachedError(f"Договор уже привязан к взаимодействию: {contract}")

    def _attach(self, contract: Contract, interaction: Interaction) -> None:
        """Привязывает договор и его headless-записи; контрагенты договора и Interaction должны совпадать."""
        contract.interaction = interaction
        contract.clean()
        contract.save(update_fields=["interaction", "updated_at"])
        for model in _HEADLESS_MODELS:
            model.objects.filter(contract=contract, interaction__isnull=True).update(interaction=interaction)


contract_attachment_service = ContractAttachmentService()
