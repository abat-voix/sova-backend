from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.interactions.models import Contract
from sova.interactions.tests.factories import ContractFactory, ResponsibleFactory


class ContractFileApiTestCase(TemporaryMediaMixin, APITestCase):
    """Тесты журнала файлов договора /api/interactions/contract-files/."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)

    def _upload(self, contract: Contract, filename: str):
        return self.client.patch(
            path=reverse("interactions:contract-detail", args=[contract.pk]),
            data={"file": SimpleUploadedFile(filename, filename.encode(), "application/pdf")},
            format="multipart",
        )

    def test_list_filtered_by_contract_shows_all_versions(self) -> None:
        """Список по `?contract=` показывает все версии, самая новая — текущая."""
        contract = ContractFactory()
        self._upload(contract, "v1.pdf")
        self._upload(contract, "v2.pdf")

        response = self.client.get(
            reverse("interactions:contract-file-list"), data={"contract": str(contract.pk)},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertEqual(len(results), 2)
        current = next(r for r in results if r["original_name"] == "v2.pdf")
        previous = next(r for r in results if r["original_name"] == "v1.pdf")
        self.assertTrue(current["is_current"])
        self.assertFalse(previous["is_current"])

    def test_download_returns_previous_version(self) -> None:
        """Прежнюю версию можно скачать даже после того, как договор её перестал ссылаться."""
        contract = ContractFactory()
        self._upload(contract, "v1.pdf")
        self._upload(contract, "v2.pdf")

        previous = contract.files.get(original_name="v1.pdf")
        response = self.client.get(
            reverse("interactions:contract-file-download", args=[previous.pk]),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_foreign_contract_files_are_not_visible(self) -> None:
        """Файлы чужого договора не видны ни в списке, ни на скачивании."""
        UserRole.objects.filter(user=self.user).delete()
        UserRole.objects.create(user=self.user, role=SystemRole.KAM)

        foreign_kam = UserFactory()
        UserRole.objects.create(user=foreign_kam, role=SystemRole.KAM)
        responsible = ResponsibleFactory(manager=foreign_kam)
        foreign_contract = ContractFactory(interaction=responsible.interaction)
        self._upload_as_admin(foreign_contract, "secret.pdf")
        foreign_file = foreign_contract.files.get()

        list_response = self.client.get(
            reverse("interactions:contract-file-list"),
            data={"contract": str(foreign_contract.pk)},
        )
        self.assertEqual(list_response.data["count"], 0)

        download_response = self.client.get(
            reverse("interactions:contract-file-download", args=[foreign_file.pk]),
        )
        self.assertEqual(download_response.status_code, status.HTTP_404_NOT_FOUND)

    def _upload_as_admin(self, contract: Contract, filename: str):
        """Загружает файл от имени администратора платформы (обходит видимость КАМа)."""
        admin = UserFactory()
        UserRole.objects.create(user=admin, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=admin)
        response = self._upload(contract, filename)
        self.client.force_authenticate(user=self.user)
        return response
