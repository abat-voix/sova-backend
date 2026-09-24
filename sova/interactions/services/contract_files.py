from sova.core.files import guess_content_type
from sova.interactions.models import Contract, ContractFile


def record_contract_file(contract: Contract, user) -> ContractFile:
    """
    Записывает в журнал файл, который сейчас лежит в `contract.file`.

    Вызывается после сохранения договора, если запрос принёс новый файл. Новая запись
    указывает на тот же ключ хранилища, что и `contract.file` — файл не копируется, поэтому
    у него нет отдельной стоимости хранения и он не расходится с текущим состоянием
    договора. Имя, размер и MIME-тип восстанавливаются из исходного имени файла
    (`contract.file_name`, заполняется сериализатором при загрузке).
    """
    return ContractFile.objects.create(
        contract=contract,
        file=contract.file.name,
        original_name=contract.file_name or contract.file.name,
        size=contract.file.size,
        content_type=guess_content_type(contract.file_name or contract.file.name),
        uploaded_by=user if getattr(user, "is_authenticated", False) else None,
    )
