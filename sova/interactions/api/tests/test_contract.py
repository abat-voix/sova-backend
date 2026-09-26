from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.interactions.models import Contract, Responsible
from sova.interactions.services.contract_attachment import contract_attachment_service
from sova.interactions.tests.factories import ContractFactory, InteractionFactory, ResponsibleFactory


class ContractApiTestCase(TemporaryMediaMixin, BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/interactions/contracts/."""

    url_basename = "interactions:contract"
    model = Contract

    def setUp(self) -> None:
        """Администратор платформы видит все взаимодействия — видимость не сужает выборку."""
        super().setUp()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)

    def create_instance(self, **kwargs) -> Contract:
        """Создаёт договор."""
        return ContractFactory(**kwargs)

    def get_expected_data(self, instance: Contract) -> dict:
        """Поля read-представления договора."""
        return {
            "id": str(instance.pk),
            "contract_number": instance.contract_number,
            "sent_at": instance.sent_at and instance.sent_at.isoformat(),
            "corrected_at": instance.corrected_at and instance.corrected_at.isoformat(),
            "signed_at": instance.signed_at and instance.signed_at.isoformat(),
            "interaction": {
                "id": str(instance.interaction_id),
                "university": {
                    "id": str(instance.interaction.university_id),
                    "name": instance.interaction.university.name,
                },
                "b2c_client": None,
            },
            "download_url": (
                reverse("interactions:contract-download", args=[instance.pk])
                if instance.file
                else None
            ),
        }

    def get_post_data(self) -> dict:
        """Данные создания договора (взаимодействие — по id)."""
        return {
            "contract_number": "Д-100",
            "sent_at": "2026-03-01",
            "interaction": str(InteractionFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления договора."""
        return {"contract_number": "Д-101", "signed_at": "2026-04-01"}

    def get_search_term(self, instance: Contract) -> str:
        """Поиск по номеру договора."""
        return instance.contract_number

    def test_add_accepts_file_upload(self) -> None:
        """Договор создаётся с файлом через multipart-запрос."""
        upload = SimpleUploadedFile("contract.pdf", b"%PDF-1.4", "application/pdf")

        response = self.client.post(
            path=self.list_url,
            data={"interaction": str(InteractionFactory().pk), "file": upload},
            format="multipart",
        )

        # Проверяем, что файл сохранён и попал в журнал, а ссылка на скачивание отдана в ответе
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        contract = Contract.objects.get(pk=response.data["id"])
        self.assertTrue(contract.file.name.endswith(".pdf"))
        self.assertEqual(contract.file_name, "contract.pdf")
        self.assertEqual(
            response.data["download_url"],
            reverse("interactions:contract-download", args=[contract.pk]),
        )
        self.assertEqual(contract.files.count(), 1)
        self.assertEqual(contract.files.get().original_name, "contract.pdf")

    def test_reupload_keeps_previous_file_in_history(self) -> None:
        """Повторная загрузка файла не теряет прежний — обе версии в журнале, обе скачиваются."""
        contract = ContractFactory()
        self.client.patch(
            path=self.detail_url(contract),
            data={"file": SimpleUploadedFile("v1.pdf", b"v1", "application/pdf")},
            format="multipart",
        )

        response = self.client.patch(
            path=self.detail_url(contract),
            data={"file": SimpleUploadedFile("v2.pdf", b"v2", "application/pdf")},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.file_name, "v2.pdf")
        self.assertEqual(contract.files.count(), 2)
        names = set(contract.files.values_list("original_name", flat=True))
        self.assertEqual(names, {"v1.pdf", "v2.pdf"})

    def test_download_returns_current_file(self) -> None:
        """Скачивание договора отдаёт текущий файл под исходным именем."""
        upload = SimpleUploadedFile("Договор.pdf", b"content", "application/pdf")
        create_response = self.client.post(
            path=self.list_url,
            data={"interaction": str(InteractionFactory().pk), "file": upload},
            format="multipart",
        )

        response = self.client.get(create_response.data["download_url"])

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_download_returns_404_without_file(self) -> None:
        """У договора без файла скачивать нечего — 404, а не 500."""
        contract = ContractFactory()

        response = self.client.get(
            reverse("interactions:contract-download", args=[contract.pk]),
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_contract_is_not_visible(self) -> None:
        """Договор чужого КАМа не виден в списке, детально и на скачивании (404)."""
        UserRole.objects.filter(user=self.user).delete()
        UserRole.objects.create(user=self.user, role=SystemRole.KAM)

        foreign_kam = UserFactory()
        UserRole.objects.create(user=foreign_kam, role=SystemRole.KAM)
        responsible = ResponsibleFactory(manager=foreign_kam)
        foreign_contract = ContractFactory(interaction=responsible.interaction)

        self.assertEqual(self.client.get(self.list_url).data["count"], 0)
        self.assertEqual(
            self.client.get(self.detail_url(foreign_contract)).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        create_response = self.client.post(
            path=self.list_url,
            data={"interaction": str(responsible.interaction_id)},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interaction", create_response.data)

    def test_add_returns_400_when_signed_before_sent(self) -> None:
        """Подписание раньше отправки на подписание возвращает 400."""
        response = self.client.post(
            path=self.list_url,
            data={
                "interaction": str(InteractionFactory().pk),
                "sent_at": "2026-03-10",
                "signed_at": "2026-03-01",
            },
            format="json",
        )

        # Проверяем, что нарушение порядка шагов 4→6 отклонено
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_without_interaction(self) -> None:
        """Через API договор без взаимодействия не создаётся (headless — только импортом)."""
        response = self.client.post(
            path=self.list_url,
            data={"contract_number": "Д-102"},
            format="json",
        )

        # Проверяем, что interaction обязателен, хотя в модели он nullable
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interaction", response.data)

    def test_change_returns_400_when_correction_after_signing(self) -> None:
        """PATCH с корректировкой позже подписания возвращает 400."""
        instance = ContractFactory(signed_at=date(2026, 3, 1))

        response = self.client.patch(
            path=self.detail_url(instance),
            data={"corrected_at": "2026-03-05"},
            format="json",
        )

        # Проверяем, что при PATCH учитываются даты, уже сохранённые в договоре
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_interaction_ids(self) -> None:
        """Фильтр interaction__ids возвращает договоры указанных взаимодействий."""
        target = ContractFactory()
        ContractFactory()

        response = self.client.get(
            path=self.list_url,
            data={"interaction__ids": str(target.interaction_id)},
        )

        # Проверяем, что найден только договор выбранного взаимодействия
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_is_signed(self) -> None:
        """Фильтр is_signed=true возвращает только подписанные договоры."""
        signed = ContractFactory(signed_at=date(2026, 3, 1))
        ContractFactory()

        response = self.client.get(path=self.list_url, data={"is_signed": "true"})

        # Проверяем, что найден только подписанный договор
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(signed.pk)],
        )

    def test_filter_by_signed_period(self) -> None:
        """Фильтры signed_at__gte/signed_at__lte ограничивают период подписания."""
        inside = ContractFactory(signed_at=date(2026, 3, 15))
        ContractFactory(signed_at=date(2025, 1, 1))
        ContractFactory(signed_at=date(2026, 12, 1))

        response = self.client.get(
            path=self.list_url,
            data={"signed_at__gte": "2026-03-01", "signed_at__lte": "2026-03-31"},
        )

        # Проверяем, что найден только договор внутри периода
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(inside.pk)],
        )


class ContractCurrentResponsiblesApiTestCase(APITestCase):
    """current_responsibles договора — действующие КАМы headless-договора из реестра."""

    def setUp(self) -> None:
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=user)
        self.kam = UserFactory(first_name="Максим", last_name="Менеджеров")
        self.university = UniversityFactory()

    def _get(self, contract: Contract) -> dict:
        response = self.client.get(path=reverse("interactions:contract-detail", args=[contract.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_headless_contract_shows_its_kams(self) -> None:
        contract = ContractFactory(interaction=None, university=self.university)
        Responsible.objects.create(contract=contract, manager=self.kam)

        data = self._get(contract)

        # Проверяем КАМа договора и отсутствие старых полей подсказки
        self.assertEqual([item["manager"]["id"] for item in data["current_responsibles"]], [self.kam.pk])
        self.assertNotIn("suggested_manager", data)
        self.assertNotIn("draft_manager_full_name", data)

    def test_closed_kam_is_not_shown(self) -> None:
        contract = ContractFactory(interaction=None, university=self.university)
        Responsible.objects.create(contract=contract, manager=self.kam, unassigned_at=timezone.now())

        # Проверяем, что снятый КАМ не показывается
        self.assertEqual(self._get(contract)["current_responsibles"], [])

    def test_attached_contract_keeps_registry_kams(self) -> None:
        contract = ContractFactory(interaction=None, university=self.university)
        Responsible.objects.create(contract=contract, manager=self.kam)
        contract_attachment_service.attach_to_new_interaction(contract=contract, author=None)

        # Проверяем: КАМы из реестра не перешли на взаимодействие и остались на договоре
        self.assertEqual([item["manager"]["id"] for item in self._get(contract)["current_responsibles"]], [self.kam.pk])
