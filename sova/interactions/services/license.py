from datetime import date

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from sova.interactions.models import Contract, InteractionProduct, License


class LicenseService:
    """
    Выдача лицензии на продукт взаимодействия с сохранением истории версий.

    Перезаключение не перезаписывает лицензию: прежняя действующая закрывается
    (`is_active=False`, `superseded_at`), создаётся новая. Ограничение БД
    `one_active_license_per_contract_interaction_product` допускает только одну
    действующую лицензию на пару (договор, продукт).
    """

    @transaction.atomic
    def create_license(
        self,
        contract: Contract,
        interaction_product: InteractionProduct,
        signed_at: date | None,
        valid_until_year: int | None,
        is_signed: bool,
        created_by: AbstractBaseUser | None,
    ) -> License:
        """Закрывает действующую лицензию пары (если есть) и создаёт новую."""
        License.objects.filter(
            contract=contract,
            interaction_product=interaction_product,
            is_active=True,
        ).update(
            is_active=False,
            superseded_at=timezone.now(),
        )
        return License.objects.create(
            contract=contract,
            interaction_product=interaction_product,
            signed_at=signed_at,
            valid_until_year=valid_until_year,
            is_signed=is_signed,
            created_by=created_by,
        )


license_service = LicenseService()
