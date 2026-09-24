from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.interactions.tests.factories import ResponsibleFactory
from sova.processes.models import ActionAttachment
from sova.processes.tests.factories import ActionAttachmentFactory, ActionInstanceFactory


class ActionAttachmentApiTestCase(TemporaryMediaMixin, BaseApiTestMixin, APITestCase):
    """Тесты чтения и загрузки вложений /api/processes/action-attachments/."""

    url_basename = "processes:action-attachment"
    model = ActionAttachment
    allow_update = False
    allow_delete = False

    def setUp(self) -> None:
        """Администратор платформы видит все взаимодействия — видимость не сужает выборку."""
        super().setUp()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)

    def create_instance(self, **kwargs) -> ActionAttachment:
        """Создаёт вложение."""
        return ActionAttachmentFactory(**kwargs)

    def get_expected_data(self, instance: ActionAttachment) -> dict:
        """Поля read-представления вложения."""
        return {
            "id": str(instance.pk),
            "action_instance": str(instance.action_instance_id),
            "uploaded_by": None,
            "download_url": reverse(
                "processes:action-attachment-download", args=[instance.pk],
            ),
        }

    def get_post_data(self) -> dict:
        """Данные загрузки — multipart, поэтому основной тест создаёт свой запрос."""
        return {}

    def upload(self, filename: str, action_instance=None):
        """Загружает файл с указанным именем во вложения действия."""
        action_instance = action_instance or ActionInstanceFactory()
        return self.client.post(
            path=self.list_url,
            data={
                "action_instance": str(action_instance.pk),
                "file": SimpleUploadedFile(filename, b"content"),
            },
            format="multipart",
        )

    def test_add_creates_instance(self) -> None:
        """Загрузка допустимого файла создаёт вложение с автором из запроса."""
        response = self.upload("report.pdf")

        # Проверяем, что вложение создано
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        attachment = ActionAttachment.objects.get(pk=response.data["id"])
        self.assertTrue(attachment.file.name.endswith(".pdf"))
        # Проверяем автора и ссылку на скачивание в ответе
        self.assertEqual(response.data["uploaded_by"]["id"], self.user.pk)
        self.assertEqual(
            response.data["download_url"],
            reverse("processes:action-attachment-download", args=[attachment.pk]),
        )

    def test_add_accepts_all_allowed_extensions(self) -> None:
        """Принимаются все форматы из ТЗ, независимо от регистра расширения."""
        action_instance = ActionInstanceFactory()
        allowed = [
            "a.png", "a.jpg", "a.jpeg", "a.PDF", "a.zip", "a.gz", "a.gzip",
            "a.rar", "a.doc", "a.docx", "a.xls", "a.XLSX",
        ]

        statuses = {
            name: self.upload(name, action_instance).status_code for name in allowed
        }

        # Проверяем, что ни один допустимый формат не отклонён
        self.assertEqual(
            {name: code for name, code in statuses.items() if code != 201},
            {},
        )

    def test_add_returns_400_for_disallowed_extension(self) -> None:
        """Файл недопустимого формата отклоняется, вложение не создаётся."""
        response = self.upload("script.exe")

        # Проверяем, что ошибка привязана к полю file и запись не создана
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)
        self.assertFalse(ActionAttachment.objects.exists())

    def test_add_returns_400_for_double_extension_with_disallowed_tail(self) -> None:
        """Проверяется последнее расширение: report.pdf.exe отклоняется."""
        response = self.upload("report.pdf.exe")

        # Проверяем, что двойное расширение не обходит проверку
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_stores_original_name_under_uuid_key(self) -> None:
        """Ключ файла в хранилище — UUID, исходное (в т.ч. кириллическое) имя — в БД."""
        response = self.upload("Договор Иванов.pdf")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        attachment = ActionAttachment.objects.get(pk=response.data["id"])
        self.assertEqual(attachment.original_name, "Договор Иванов.pdf")
        self.assertEqual(attachment.content_type, "application/pdf")
        self.assertEqual(attachment.size, len(b"content"))
        # Ключ не содержит исходного имени
        self.assertNotIn("Договор", attachment.file.name)
        self.assertNotIn("Иванов", attachment.file.name)
        self.assertTrue(attachment.file.name.endswith(".pdf"))

    def test_add_returns_400_for_file_over_size_limit(self) -> None:
        """Файл больше `FILE_UPLOAD_MAX_SIZE` отклоняется, вложение не создаётся."""
        action_instance = ActionInstanceFactory()
        oversized = SimpleUploadedFile("big.pdf", b"x" * 10, content_type="application/pdf")

        with override_settings(FILE_UPLOAD_MAX_SIZE=5):
            response = self.client.post(
                path=self.list_url,
                data={"action_instance": str(action_instance.pk), "file": oversized},
                format="multipart",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ActionAttachment.objects.exists())

    def test_download_returns_file_under_original_name(self) -> None:
        """Скачивание отдаёт файл с исходным именем в Content-Disposition, а не UUID-ключом."""
        upload_response = self.upload("Договор.pdf")
        attachment = ActionAttachment.objects.get(pk=upload_response.data["id"])

        response = self.client.get(upload_response.data["download_url"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertNotIn(attachment.file.name, response["Content-Disposition"])

    def test_foreign_attachment_is_not_visible(self) -> None:
        """Вложение чужого КАМа не видно в списке, детально и на скачивании (404)."""
        UserRole.objects.filter(user=self.user).delete()
        UserRole.objects.create(user=self.user, role=SystemRole.KAM)

        foreign_kam = UserFactory()
        UserRole.objects.create(user=foreign_kam, role=SystemRole.KAM)
        responsible = ResponsibleFactory(manager=foreign_kam)
        action_instance = ActionInstanceFactory(
            stage_instance__workflow_instance__interaction=responsible.interaction,
        )
        foreign_attachment = ActionAttachmentFactory(action_instance=action_instance)

        self.assertEqual(
            self.client.get(self.list_url).data["count"], 0,
        )
        self.assertEqual(
            self.client.get(self.detail_url(foreign_attachment)).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        download_url = reverse(
            "processes:action-attachment-download", args=[foreign_attachment.pk],
        )
        self.assertEqual(
            self.client.get(download_url).status_code, status.HTTP_404_NOT_FOUND,
        )
        upload_response = self.upload("new.pdf", action_instance)
        self.assertEqual(upload_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("action_instance", upload_response.data)

    def test_filters_select_matching_attachments(self) -> None:
        """Фильтры экземпляра действия и автора выбирают нужные вложения."""
        author = UserFactory()
        target = ActionAttachmentFactory(uploaded_by=author)
        ActionAttachmentFactory()

        def ids(params: dict) -> list[str]:
            response = self.client.get(path=self.list_url, data=params)
            return [item["id"] for item in response.data["results"]]

        # Проверяем каждый фильтр
        self.assertEqual(
            ids({"action_instance__ids": str(target.action_instance_id)}),
            [str(target.pk)],
        )
        self.assertEqual(ids({"uploaded_by__ids": str(author.pk)}), [str(target.pk)])
