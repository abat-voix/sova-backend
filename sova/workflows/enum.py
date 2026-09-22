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
    CONTACT_PERSON_LINK = "contact_person.link", "Привязать контакт"
    CONTACT_PERSON_UPDATE = "contact_person.update", "Изменить контакт"
    CONTACT_PERSON_DEACTIVATE = "contact_person.deactivate", "Деактивировать контакт"

    RESPONSIBLE_ASSIGN = "responsible.assign", "Назначить ответственного"
    RESPONSIBLE_UNASSIGN = "responsible.unassign", "Снять ответственного"

    INTERACTION_DIRECTION_ADD = "interaction_direction.add", "Добавить направление"
    INTERACTION_DIRECTION_REMOVE = "interaction_direction.remove", "Убрать направление"
    INTERACTION_PROGRAM_ADD = "interaction_program.add", "Добавить программу"
    INTERACTION_PROGRAM_REMOVE = "interaction_program.remove", "Убрать программу"
    INTERACTION_PRODUCT_ADD = "interaction_product.add", "Добавить продукт"
    INTERACTION_PRODUCT_REMOVE = "interaction_product.remove", "Убрать продукт"

    CONTRACT_CREATE = "contract.create", "Создать договор"
    CONTRACT_UPDATE = "contract.update", "Изменить договор"
    CONTRACT_SIGN = "contract.sign", "Подписать договор"
    CONTRACT_FILE_UPLOAD = "contract.file.upload", "Загрузить файл договора"
    CONTRACT_MARK_SENT = "contract.mark_sent", "Отметить отправку договора"
    CONTRACT_MARK_CORRECTED = "contract.mark_corrected", "Отметить доработку договора"

    LICENSE_CREATE = "license.create", "Создать лицензию"
    LICENSE_UPDATE = "license.update", "Изменить лицензию"

    COMMUNICATION_CREATE = "communication.create", "Создать коммуникацию"
    MEETING_CREATE = "meeting.create", "Создать встречу"
    INSTALLATION_CREATE = "installation.create", "Создать установку"
    TRAINING_CREATE = "training.create", "Создать обучение"
    PROGRAM_UPDATE_CREATE = "program_update.create", "Создать обновление программы"
    RESULT_CHECK_CREATE = "result_check.create", "Создать проверку результата"

    CHECKLIST_FILL = "checklist.fill", "Заполнить чек-лист"
    EMAIL_SEND = "email.send", "Отправить письмо"
    LINK_ATTACH = "link.attach", "Добавить ссылку"
    REMINDER_CREATE = "reminder.create", "Создать напоминание"
