from django.db import transaction

from accounts.policy import Action, can
from sova.catalog.enum import PersonalDataAccessAction
from sova.catalog.models import B2CClient, B2CClientAddress, B2CClientAddressAccessLog

# Открытые части адреса — меняются вместе с карточкой клиента
OPEN_FIELDS = ("country_code", "region", "city")
# Персональные данные — только по праву `catalog.personal_data.*`, с записью в журнал
PERSONAL_FIELDS = ("street", "house", "apartment", "postal_code")


class B2CClientAddressService:
    """
    Адрес регистрации B2C-клиента (физлица). Страна, регион и город открыты и сохраняются вместе с карточкой.
    Улица, дом, квартира и индекс — персональные данные: читает и меняет их только администратор платформы, каждое
    обращение пишется в `B2CClientAddressAccessLog` (приказ ФСТЭК № 117).
    """

    @staticmethod
    def can_read(user) -> bool:
        return can(user, Action.CATALOG_PERSONAL_DATA_READ)

    @staticmethod
    def get(client: B2CClient) -> B2CClientAddress:
        """Адрес клиента; если его ещё нет — пустой, несохранённый."""
        return B2CClientAddress.objects.filter(b2c_client=client).first() or B2CClientAddress(b2c_client=client)

    @transaction.atomic
    def save_open(self, client: B2CClient, values: dict | None) -> None:
        """Сохраняет открытые части адреса; `None` очищает их, персональные части не трогает."""
        address = self.get(client)
        updates = dict.fromkeys(OPEN_FIELDS, "") if values is None else values
        for field in OPEN_FIELDS:
            if field in updates:
                setattr(address, field, updates[field])
        if address.pk is None and not any(getattr(address, field) for field in OPEN_FIELDS):
            return
        address.full_clean()
        address.save()

    def read_personal(self, client: B2CClient, user, request=None) -> B2CClientAddress:
        """Адрес целиком для просмотра; выдача пишется в журнал."""
        address = self.get(client)
        self.log_access(user=user, client=client, fields=PERSONAL_FIELDS, request=request)
        return address

    @transaction.atomic
    def save_personal(self, client: B2CClient, values: dict, user, request=None) -> B2CClientAddress:
        """Меняет персональные части адреса; изменение пишется в журнал."""
        address = self.get(client)
        changed = [field for field in PERSONAL_FIELDS if field in values]
        for field in changed:
            setattr(address, field, values[field])
        address.full_clean()
        address.save()
        self.log_access(
            user=user, client=client, fields=changed, action=PersonalDataAccessAction.UPDATE, request=request
        )
        return address

    @staticmethod
    def log_access(
        user,
        client: B2CClient,
        fields,
        action: str = PersonalDataAccessAction.READ,
        request=None,
    ) -> B2CClientAddressAccessLog:
        """Записывает обращение к персональным частям адреса в журнал."""
        return B2CClientAddressAccessLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            b2c_client=client,
            fields=list(fields),
            action=action,
            ip=(request.META.get("REMOTE_ADDR") or None) if request is not None else None,
        )


b2c_client_address_service = B2CClientAddressService()
