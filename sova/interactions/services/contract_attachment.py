from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from accounts.models import SystemRole
from accounts.services import get_system_role
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
    def attach_to_new_interaction(self, contract: Contract, author: AbstractBaseUser | None) -> Interaction:
        """
        Создаёт новый Interaction из headless-договора и переносит на него все его записи.

        Ответственные — как при обычном создании взаимодействия: автор-КАМ становится ответственным, у руководителя
        и администратора взаимодействие остаётся ничьим до назначения через `assign-responsible`. КАМы договора из
        реестра на взаимодействие не переходят: они остаются на договоре подсказкой для назначения
        (`assignment_candidates`).
        """
        self._check_headless(contract=contract)
        interaction = Interaction.objects.create(
            university=contract.university,
            b2c_client=contract.b2c_client,
            comment=contract.draft_comment,
        )
        self._attach(contract=contract, interaction=interaction)

        if author is not None and get_system_role(author) == SystemRole.KAM:
            responsible_service.assign(interaction=interaction, manager=author, assigned_by=author)

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
