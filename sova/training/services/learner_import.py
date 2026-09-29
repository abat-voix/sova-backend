from django.db import transaction

from sova.catalog.enum import CatalogType
from sova.catalog.exceptions import CatalogImportError
from sova.catalog.schemas import CATALOG_IMPORT_FIELDS, ImportRowWarning
from sova.catalog.services.import_file import ImportSource, import_file_service
from sova.core.text import text_key
from sova.training.enum import EducationLevel, Gender, TrainingApplicationStatus
from sova.training.exceptions import TrainingError
from sova.training.models import Learner, LearnerPersonalData, TrainingApplication, TrainingApplicationLearner, TrainingStream
from sova.training.schemas import LearnerImportResult
from sova.training.services.application import training_application_service
from sova.training.services.learner_matching import learner_matching_service

_LEARNER_FIELDS = ("last_name", "first_name", "middle_name", "email", "phone")
_DATE_FIELDS = frozenset({"birth_date", "passport_issued_at", "diploma_issued_at"})
_GENDERS = {
    **dict.fromkeys(("м", "муж", "мужской", "male"), Gender.MALE),
    **dict.fromkeys(("ж", "жен", "женский", "female"), Gender.FEMALE),
}
_EDUCATION_LEVELS = {text_key(label): value for value, label in EducationLevel.choices}


class LearnerImportService:
    """
    Загрузка файла «Пользователи»: обучающиеся и их персональные данные, при выбранном потоке — заявка.

    Чтение файла, маппинг колонок (`CatalogType.LEARNER`, /api/catalog/import-mappings/) и построчная обработка —
    общие с импортом каталогов (`import_file_service`). Загрузка «всё или ничего»: ошибка в любой строке откатывает
    файл целиком, в том числе заявку.

    Обучающийся ищется по email, затем по телефону; не найден — создаётся. Как в импорте каталогов: колонки нет
    в файле — поле не меняется, ячейка пуста — значение стирается. С потоком: создаётся одна заявка, обучающиеся становятся её участниками; кто уже участник действующей
    заявки этого потока — пропускается с предупреждением.
    """

    @transaction.atomic
    def import_file(self, source: ImportSource, user, stream: TrainingStream | None = None) -> LearnerImportResult:
        if stream is not None:
            training_application_service.check_stream_open(stream)
        rows = import_file_service.read_mapped_rows(
            catalog_type=CatalogType.LEARNER,
            source=source,
            required=CATALOG_IMPORT_FIELDS[CatalogType.LEARNER].required,
        )
        counters = {"created": 0, "updated": 0}
        warnings: list[ImportRowWarning] = []
        application: TrainingApplication | None = None

        def handle(row_number: int, row: dict) -> None:
            nonlocal application
            learner, created, messages = self._upsert(values=self._to_fields(row))
            counters["created" if created else "updated"] += 1
            if stream is not None:
                if self._in_stream(learner=learner, stream=stream):
                    messages.append(f"обучающийся {learner} уже есть в заявке этого потока — пропущен")
                else:
                    if application is None:
                        application = training_application_service.create_application(stream=stream, user=user)
                    training_application_service.add_learner(application=application, learner=learner)
            warnings.extend(ImportRowWarning(row_number=row_number, message=message) for message in messages)

        import_file_service.process_numbered_rows(rows=rows, handler=handle)
        return LearnerImportResult(
            created=counters["created"],
            updated=counters["updated"],
            warnings=warnings,
            application=application,
        )

    @staticmethod
    def _to_fields(row: dict) -> dict:
        """Строка файла с каноническими ключами → значения полей; пустая ячейка — пустое значение (стирает поле)."""
        values = {}
        for field, raw in row.items():
            if raw in (None, ""):
                values[field] = None if field in _DATE_FIELDS else ""
                continue
            if field in _DATE_FIELDS:
                value = import_file_service.to_date(raw)
                if value is None:
                    raise ValueError(f"не распознана дата в поле {field}: {raw}")
            elif field == "gender":
                value = _GENDERS.get(text_key(str(raw)))
                if value is None:
                    raise ValueError(f"неизвестный пол «{raw}»; допустимо: М, Ж")
            elif field == "education_level":
                value = _EDUCATION_LEVELS.get(text_key(str(raw)))
                if value is None:
                    raise ValueError(f"неизвестный уровень образования «{raw}»")
            else:
                value = import_file_service.to_text(raw)
            values[field] = value
        return values

    @staticmethod
    def _upsert(values: dict) -> tuple[Learner, bool, list[str]]:
        """Создаёт или обновляет карточку и персональные данные; возвращает (карточка, создана ли, предупреждения)."""
        if not values.get("last_name") or not values.get("first_name"):
            raise CatalogImportError("не заполнены фамилия и имя")
        if not values.get("email") and not values.get("phone"):
            raise CatalogImportError("нужен email или телефон — по ним находится обучающийся")
        try:
            learner, warnings = learner_matching_service.find(email=values.get("email", ""), phone=values.get("phone", ""))
        except TrainingError as error:
            raise CatalogImportError(str(error.detail)) from error

        learner_values = {field: values[field] for field in _LEARNER_FIELDS if field in values}
        created = learner is None
        if created:
            learner = Learner.objects.create(**learner_values)
        else:
            if warnings:
                # Найден по телефону, а email другой — email карточки не перезаписываем
                learner_values.pop("email", None)
            for field, value in learner_values.items():
                setattr(learner, field, value)
            learner.save()

        personal_values = {field: value for field, value in values.items() if field not in _LEARNER_FIELDS}
        if personal_values:
            data, _ = LearnerPersonalData.objects.get_or_create(learner=learner)
            for field, value in personal_values.items():
                setattr(data, field, value)
            data.save()
        return learner, created, list(warnings)

    @staticmethod
    def _in_stream(learner: Learner, stream: TrainingStream) -> bool:
        """Участвует ли обучающийся в действующей заявке потока."""
        return TrainingApplicationLearner.objects.filter(
            learner=learner,
            application__stream=stream,
            application__status=TrainingApplicationStatus.NEW,
        ).exists()


learner_import_service = LearnerImportService()
