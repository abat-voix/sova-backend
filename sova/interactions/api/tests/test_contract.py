from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.core.tests.media import TemporaryMediaMixin
from sova.interactions.models import Contract
from sova.interactions.tests.factories import ContractFactory, InteractionFactory


class ContractApiTestCase(TemporaryMediaMixin, BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/interactions/contracts/."""

    url_basename = "interactions:contract"
    model = Contract

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

        # Проверяем, что файл сохранён и его URL отдан в ответе
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        contract = Contract.objects.get(pk=response.data["id"])
        self.assertTrue(contract.file.name.endswith(".pdf"))
        self.assertIn(".pdf", response.data["file"])

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


class ContractSuggestedManagerApiTestCase(APITestCase):
    """suggested_manager договора — подсказка ответственного по ФИО менеджера из реестра."""

    def setUp(self) -> None:
        self.client.force_authenticate(user=UserFactory())
        self.manager = UserFactory(first_name="Максим", last_name="Менеджеров")
        self.university = UniversityFactory()

    def _get(self, contract: Contract) -> dict:
        response = self.client.get(path=reverse("interactions:contract-detail", args=[contract.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    def test_headless_contract_suggests_found_user(self) -> None:
        contract = ContractFactory(
            interaction=None, university=self.university, draft_manager_full_name="менеджеров максим"
        )

        data = self._get(contract)

        # Проверяем ФИО из реестра и подсказку-пользователя
        self.assertEqual(data["draft_manager_full_name"], "менеджеров максим")
        self.assertEqual(data["suggested_manager"]["id"], self.manager.pk)

    def test_unknown_manager_gives_null(self) -> None:
        contract = ContractFactory(interaction=None, university=self.university, draft_manager_full_name="Петров Пётр")

        # Проверяем, что подсказки нет
        self.assertIsNone(self._get(contract)["suggested_manager"])

    def test_attached_contract_gives_null(self) -> None:
        contract = ContractFactory(draft_manager_full_name="Менеджеров Максим")

        # Проверяем, что у привязанного договора подсказки нет
        self.assertIsNone(self._get(contract)["suggested_manager"])

    def test_list_suggests_for_each_headless_contract(self) -> None:
        ContractFactory(interaction=None, university=self.university, draft_manager_full_name="Менеджеров Максим")
        ContractFactory(interaction=None, university=self.university, draft_manager_full_name="Петров Пётр")

        response = self.client.get(path=reverse("interactions:contract-list"))

        # Проверяем подсказки в списке
        suggested = sorted(
            (item["draft_manager_full_name"], (item["suggested_manager"] or {}).get("id"))
            for item in response.data["results"]
        )
        self.assertEqual(suggested, [("Менеджеров Максим", self.manager.pk), ("Петров Пётр", None)])
