from django.db.models import TextChoices


class Audience(TextChoices):
    """Целевая аудитория workflow-шаблона."""

    B2B = "b2b", "Вузы"
    B2C = "b2c", "Физ/юрлица"


class WorkflowChangeType(TextChoices):
    """Тип изменения определения workflow в аудите."""

    CREATED = "created", "Создано"
    UPDATED = "updated", "Изменено"
    DELETED = "deleted", "Удалено"


class ActionFeatureCode(TextChoices):
    CONTACT_PERSON_CREATE = "contact_person.create", "Создать контакт"
    CONTACT_PERSON_SELECT = "contact_person.select", "Выбрать контакт"
    CONTRACT_CREATE = "contract.create", "Создать договор"
    CONTRACT_UPDATE = "contract.update", "Изменить договор"
    CONTRACT_SIGN = "contract.sign", "Подписать договор"
    CONTRACT_FILE_UPLOAD = "contract.file.upload", "Загрузить файл договора"
    LICENSE_CREATE = "license.create", "Создать лицензию"
    LICENSE_UPDATE = "license.update", "Изменить лицензию"
    COMMUNICATION_CREATE = "communication.create", "Создать коммуникацию"
    MEETING_CREATE = "meeting.create", "Создать встречу"
    INSTALLATION_CREATE = "installation.create", "Создать установку"
    TRAINING_CREATE = "training.create", "Создать обучение"
    PROGRAM_UPDATE_CREATE = "program_update.create", "Создать обновление программы"
    RESULT_CHECK_CREATE = "result_check.create", "Создать проверку результата"
