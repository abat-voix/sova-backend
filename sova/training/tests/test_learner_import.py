import datetime
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.enum import CatalogType
from sova.catalog.exceptions import CatalogImportError, CatalogImportRowsError
from sova.catalog.models import CatalogImportMapping
from sova.catalog.services import catalog_import_mapping_service
from sova.core.tests.factories import UserFactory
from sova.training.enum import EducationLevel, Gender, TrainingStreamStatus
from sova.training.exceptions import TrainingError
from sova.training.models import Learner, TrainingApplication
from sova.training.services.learner_import import learner_import_service
from sova.training.tests.factories import (
    LearnerFactory,
    TrainingApplicationLearnerFactory,
    TrainingStreamFactory,
)

# Заголовки как в docs/Хакатон/Загрузка пользователей.xlsx — вместе с потерянными открывающими скобками
MAPPING = {
    "last_name": "Фамилия",
    "first_name": "Имя",
    "middle_name": "Отчествопри наличии)",
    "phone": "Номер телефона",
    "email": "Email",
    "snils": "СНИЛС",
    "passport_series": "Серия паспорта",
    "passport_number": "Номер паспорта",
    "passport_issued_by": "Кем выдан паспорт",
    "passport_issued_at": "Дата выдачи паспорта",
    "passport_division_code": "Код подразделения",
    "gender": "Пол",
    "birth_date": "Дата рождения",
    "registration_region": "Регион регистрации",
    "registration_locality": "Населенный пункт регистрации",
    "registration_street": "Улица регистрации",
    "registration_house": "Дом регистрации",
    "registration_apartment": "Квартира регистрации",
    "registration_postcode": "Индекс регистрации",
    "first_name_dative": "Имядательный падеж)",
    "last_name_dative": "Фамилиядательный падеж)",
    "middle_name_dative": "Отчестводательный падеж)",
    "education_level": "Образование",
    "diploma_qualification": "Профессия по диплому",
    "diploma_institution": "Учебное заведение по диплому",
    "diploma_last_name": "Фамилия, указанная в дипломе",
    "diploma_number": "Номер диплома",
    "diploma_series": "Серия диплома",
    "diploma_registration_number": "Регистрационный номер диплома",
    "diploma_issued_at": "Дата выдачи диплома",
}
HEADERS = list(MAPPING.values())
FILE_ROWS = [
    ["Черепанова", "Светлана", "Васильевна", 79990234365, "cherepanona.s@test.ru"],
    ["Кричанов", "Максим", "Сергеевич", 79977361351, "max_crich@mail.ru"],
    ["Григорьев", "Станислав", "Семенович", 79947392263, "grigorev355@gmail.com"],
    ["Осипенко", "Ирина", "Викторовна", 79934253846, "Osipenko833484@mail.ru"],
    ["Иванов", "Михаил", "Петрович", 79924583434, "mp_ivanov@mail.ru"],
]


def xlsx(rows, headers=HEADERS) -> SimpleUploadedFile:
    workbook = Workbook()
    workbook.active.append(headers)
    for row in rows:
        workbook.active.append(row)
    content = BytesIO()
    workbook.save(content)
    return SimpleUploadedFile("users.xlsx", content.getvalue())


def full_row(**overrides) -> list:
    values = dict.fromkeys(HEADERS)
    values.update({
        "Фамилия": "Иванов", "Имя": "Михаил", "Номер телефона": 79924583434, "Email": "mp_ivanov@mail.ru",
        "СНИЛС": "123-456-789 45", "Серия паспорта": "4510", "Номер паспорта": "567890",
        "Дата выдачи паспорта": datetime.datetime(2020, 1, 15), "Пол": "М", "Дата рождения": "17.05.2000",
        "Имядательный падеж)": "Михаилу", "Образование": "Высшее образование – бакалавриат",
        "Дата выдачи диплома": datetime.datetime(2022, 7, 1),
    })
    values.update(overrides)
    return list(values.values())


def configure_mapping() -> None:
    catalog_import_mapping_service.replace_for_type(catalog_type=CatalogType.LEARNER, mappings=MAPPING)


class LearnerImportServiceTestCase(TestCase):
    def setUp(self) -> None:
        configure_mapping()
        self.user = UserFactory()

    def test_without_stream_creates_learners_only(self) -> None:
        result = learner_import_service.import_file(source=xlsx(FILE_ROWS), user=self.user)

        self.assertEqual((result.created, result.updated, result.application), (5, 0, None))
        self.assertFalse(TrainingApplication.objects.exists())
        learner = Learner.objects.get(last_name="Черепанова")
        self.assertEqual((learner.email, learner.phone), ("cherepanona.s@test.ru", "79990234365"))

    def test_with_stream_creates_application_with_all_learners(self) -> None:
        stream = TrainingStreamFactory()

        result = learner_import_service.import_file(source=xlsx(FILE_ROWS), user=self.user, stream=stream)

        application = TrainingApplication.objects.get()
        self.assertEqual(result.application, application)
        self.assertEqual((application.stream, application.created_by), (stream, self.user))
        self.assertEqual(application.participants.count(), 5)
        self.assertFalse(application.participants.filter(is_paid=True).exists())

    def test_learner_already_in_stream_is_skipped_with_warning(self) -> None:
        stream = TrainingStreamFactory()
        learner_import_service.import_file(source=xlsx(FILE_ROWS), user=self.user, stream=stream)

        result = learner_import_service.import_file(source=xlsx(FILE_ROWS), user=self.user, stream=stream)

        self.assertIsNone(result.application)
        self.assertEqual(TrainingApplication.objects.count(), 1)
        self.assertEqual(len(result.warnings), 5)
        self.assertEqual((result.created, result.updated), (0, 5))

    def test_partial_repeat_adds_only_new_learners(self) -> None:
        stream = TrainingStreamFactory()
        learner_import_service.import_file(source=xlsx(FILE_ROWS[:2]), user=self.user, stream=stream)

        result = learner_import_service.import_file(source=xlsx(FILE_ROWS), user=self.user, stream=stream)

        self.assertEqual(result.application.participants.count(), 3)
        self.assertEqual(len(result.warnings), 2)

    def test_existing_learner_found_by_email_in_other_case(self) -> None:
        learner = LearnerFactory(email="CHEREPANONA.S@test.ru")

        result = learner_import_service.import_file(source=xlsx(FILE_ROWS[:1]), user=self.user)

        self.assertEqual((result.created, result.updated), (0, 1))
        self.assertEqual(Learner.objects.get(), learner)

    def test_found_by_phone_with_other_email_warns_and_keeps_email(self) -> None:
        learner = LearnerFactory(email="old@test.ru", phone="79990234365")

        result = learner_import_service.import_file(source=xlsx(FILE_ROWS[:1]), user=self.user)

        learner.refresh_from_db()
        self.assertEqual(learner.email, "old@test.ru")
        self.assertEqual(len(result.warnings), 1)

    def test_same_name_only_is_a_new_learner(self) -> None:
        LearnerFactory(last_name="Черепанова", first_name="Светлана", email="other@test.ru", phone="70000000000")

        result = learner_import_service.import_file(source=xlsx(FILE_ROWS[:1]), user=self.user)

        self.assertEqual(result.created, 1)
        self.assertEqual(Learner.objects.count(), 2)

    def test_personal_data(self) -> None:
        learner_import_service.import_file(source=xlsx([full_row()]), user=self.user)

        data = Learner.objects.get().personal_data
        self.assertEqual(data.snils, "123-456-789 45")
        self.assertEqual(data.passport_issued_at, datetime.date(2020, 1, 15))
        self.assertEqual(data.birth_date, datetime.date(2000, 5, 17))
        self.assertEqual(data.gender, Gender.MALE)
        self.assertEqual(data.first_name_dative, "Михаилу")
        self.assertEqual(data.education_level, EducationLevel.BACHELOR)
        self.assertEqual(data.diploma_issued_at, datetime.date(2022, 7, 1))

    def test_blank_cell_erases_saved_value(self) -> None:
        """Как в импорте каталогов: пустая ячейка стирает значение."""
        learner_import_service.import_file(source=xlsx([full_row()]), user=self.user)

        learner_import_service.import_file(
            source=xlsx([full_row(**{"СНИЛС": None, "Пол": None, "Дата рождения": None, "Серия паспорта": "4511"})]),
            user=self.user,
        )

        data = Learner.objects.get().personal_data
        self.assertEqual((data.snils, data.snils_hash, data.gender), ("", "", ""))
        self.assertIsNone(data.birth_date)
        self.assertEqual(data.passport_series, "4511")

    def test_missing_column_keeps_saved_value(self) -> None:
        """Колонки нет в файле — поле не меняется."""
        learner_import_service.import_file(source=xlsx([full_row()]), user=self.user)
        without_snils = [header for header in HEADERS if header != "СНИЛС"]
        row = dict(zip(HEADERS, full_row(**{"Серия паспорта": "4511"}), strict=True))

        learner_import_service.import_file(
            source=xlsx([[row[header] for header in without_snils]], headers=without_snils), user=self.user
        )

        data = Learner.objects.get().personal_data
        self.assertEqual((data.snils, data.passport_series), ("123-456-789 45", "4511"))

    def test_row_errors_reject_whole_file(self) -> None:
        stream = TrainingStreamFactory()
        rows = [FILE_ROWS[0], [None, "Имя", None, 79990000000, "x@y.ru"], ["Петров", "Пётр", None, None, None]]

        with self.assertRaises(CatalogImportRowsError) as error:
            learner_import_service.import_file(source=xlsx(rows), user=self.user, stream=stream)

        self.assertEqual([item.row_number for item in error.exception.errors], [3, 4])
        self.assertFalse(Learner.objects.exists())
        self.assertFalse(TrainingApplication.objects.exists())

    def test_unknown_gender_is_row_error(self) -> None:
        with self.assertRaises(CatalogImportRowsError):
            learner_import_service.import_file(source=xlsx([full_row(**{"Пол": "X"})]), user=self.user)

    def test_cancelled_stream_rejected(self) -> None:
        stream = TrainingStreamFactory(status=TrainingStreamStatus.CANCELLED)

        with self.assertRaises(TrainingError) as error:
            learner_import_service.import_file(source=xlsx(FILE_ROWS), user=self.user, stream=stream)
        self.assertEqual(error.exception.error_code, "stream_cancelled")

    def test_mapping_required(self) -> None:
        CatalogImportMapping.objects.filter(catalog_type=CatalogType.LEARNER).delete()

        with self.assertRaises(CatalogImportError):
            learner_import_service.import_file(source=xlsx(FILE_ROWS), user=self.user)


class LearnerImportApiTestCase(APITestCase):
    url = "/api/training/learners/import/"

    def setUp(self) -> None:
        configure_mapping()
        self.admin = UserFactory()
        UserRole.objects.create(user=self.admin, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(self.admin)

    def test_upload_without_stream(self) -> None:
        response = self.client.post(self.url, {"file": xlsx(FILE_ROWS)}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual((response.data["created"], response.data["application"]), (5, None))

    def test_upload_with_stream(self) -> None:
        stream = TrainingStreamFactory()
        TrainingApplicationLearnerFactory(
            application__stream=stream, learner=LearnerFactory(email="mp_ivanov@mail.ru")
        )

        response = self.client.post(self.url, {"file": xlsx(FILE_ROWS), "stream": str(stream.pk)}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        application = TrainingApplication.objects.get(pk=response.data["application"])
        self.assertEqual(application.participants.count(), 4)
        self.assertEqual(response.data["warnings"][0]["row"], 6)

    def test_row_errors_format(self) -> None:
        response = self.client.post(self.url, {"file": xlsx([[None, "Имя", None, 1, "a@b.ru"]])}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "import_failed")
        self.assertEqual(response.data["errors"][0]["row"], 2)

    def test_cancelled_stream_is_conflict(self) -> None:
        stream = TrainingStreamFactory(status=TrainingStreamStatus.CANCELLED)

        response = self.client.post(self.url, {"file": xlsx(FILE_ROWS), "stream": str(stream.pk)}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "stream_cancelled")

    def test_only_platform_admin(self) -> None:
        kam = UserFactory()
        UserRole.objects.create(user=kam, role=SystemRole.KAM)
        self.client.force_authenticate(kam)

        response = self.client.post(self.url, {"file": xlsx(FILE_ROWS)}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_catalog_import_does_not_accept_learner_type(self) -> None:
        response = self.client.post(
            "/api/catalog/imports/", {"catalog_type": "learner", "file": xlsx(FILE_ROWS)}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("catalog_type", response.data)

    def test_learner_mapping_is_configurable(self) -> None:
        response = self.client.get("/api/catalog/import-mappings/by-type/learner/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        required = {item["target_field"] for item in response.data if item["required"]}
        self.assertEqual(required, {"first_name", "last_name"})
