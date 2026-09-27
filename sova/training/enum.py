from django.db.models import TextChoices


class TrainingStreamStatus(TextChoices):
    """Статус потока обучения."""

    DRAFT = "draft", "Черновик"
    ENROLLMENT_OPEN = "enrollment_open", "Идёт набор"
    IN_PROGRESS = "in_progress", "Идёт обучение"
    COMPLETED = "completed", "Завершён"
    CANCELLED = "cancelled", "Отменён"


class TrainingApplicationStatus(TextChoices):
    """Статус заявки на поток."""

    NEW = "new", "Новая"
    CANCELLED = "cancelled", "Отменена"


class AcademicDegree(TextChoices):
    NONE = "none", "Нет"
    CANDIDATE = "candidate", "Кандидат наук"
    DOCTOR = "doctor", "Доктор наук"


class AcademicTitle(TextChoices):
    NONE = "none", "Нет"
    DOCENT = "docent", "Доцент"
    PROFESSOR = "professor", "Профессор"


class QualificationKind(TextChoices):
    """Вид подготовки преподавателя (шаги 9 и 13 ТЗ)."""

    INITIAL = "initial", "Обучение преподавателей"
    ADVANCED = "advanced", "Повышение квалификации"


class QualificationDocumentType(TextChoices):
    CERTIFICATE = "certificate", "Сертификат"
    DIPLOMA = "diploma", "Удостоверение"
    OTHER = "other", "Другое"


class Gender(TextChoices):
    MALE = "male", "Мужской"
    FEMALE = "female", "Женский"


class EducationLevel(TextChoices):
    """Уровень образования — справочник Лист2 файла загрузки обучающихся."""

    NONE = "none", "Без образования"
    BASIC_GENERAL = "basic_general", "Основное общее образование - 9 классов"
    SECONDARY_GENERAL = "secondary_general", "Среднее общее образование - 11 классов"
    SECONDARY_VOCATIONAL = "secondary_vocational", "Среднее профессиональное образование"
    BACHELOR = "bachelor", "Высшее образование – бакалавриат"
    SPECIALIST_MASTER = "specialist_master", "Высшее образование – специалитет, магистратура"
    HIGHER_QUALIFICATION = "higher_qualification", "Высшее образование – подготовка кадров высшей квалификации"


class PersonalDataAccessAction(TextChoices):
    READ = "read", "Просмотр"
    EXPORT = "export", "Выгрузка"
