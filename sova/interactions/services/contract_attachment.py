from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from sova.interactions.exceptions import (
    AmbiguousManagerError,
    ContractAlreadyAttachedError,
    ManagerNotFoundError,
)
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
    def attach_to_new_interaction(self, contract: Contract, assigned_by: AbstractBaseUser | None) -> Interaction:
        """Создаёт новый Interaction из headless-договора и переносит на него все его записи."""
        self._check_headless(contract=contract)
        interaction = Interaction.objects.create(
            university=contract.university,
            b2c_client=contract.b2c_client,
            comment=contract.draft_comment,
        )
        self._attach(contract=contract, interaction=interaction)

        if contract.draft_manager_full_name:
            manager = self._resolve_manager(contract.draft_manager_full_name)
            responsible_service.assign(interaction=interaction, manager=manager, assigned_by=assigned_by)

        return interaction

    @transaction.atomic
    def attach_to_existing_interaction(self, contract: Contract, interaction: Interaction) -> None:
        """Привязывает дополнительный договор к уже существующему Interaction (переиздание/расширение)."""
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

    def _resolve_manager(self, full_name: str) -> AbstractBaseUser:
        """
        Сравнивает с User по first_name/last_name в обоих порядках слов.

        ФИО в файле обычно пишут «Фамилия Имя» (`draft_manager_full_name`), а
        `User.get_full_name()` в Django — «Имя Фамилия». Точное сравнение с `get_full_name()` не
        сработало бы почти никогда — сравниваем с обоими порядками, без учёта регистра и лишних
        пробелов. Отчества в `User` нет, поэтому ФИО с отчеством в файле резолв не найдёт.
        """
        normalized = self._normalize(full_name)
        candidates = [
            user for user in get_user_model().objects.filter(is_active=True) if normalized in self._name_variants(user)
        ]
        if not candidates:
            raise ManagerNotFoundError(f"Менеджер не найден: {full_name}")
        if len(candidates) > 1:
            raise AmbiguousManagerError(f"Менеджер неоднозначен: {full_name}")
        return candidates[0]

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).casefold()

    @classmethod
    def _name_variants(cls, user: AbstractBaseUser) -> set[str]:
        first, last = user.first_name, user.last_name
        return {cls._normalize(f"{first} {last}"), cls._normalize(f"{last} {first}")}


contract_attachment_service = ContractAttachmentService()
