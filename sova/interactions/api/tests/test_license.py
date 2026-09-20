from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.interactions.models import License
from sova.interactions.tests.factories import (
    ContractFactory,
    InteractionProductFactory,
    LicenseFactory,
)


class LicenseApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/interactions/licenses/."""

    url_basename = "interactions:license"
    model = License

    def create_instance(self, **kwargs) -> License:
        """Создаёт лицензию."""
        return LicenseFactory(**kwargs)

    def get_expected_data(self, instance: License) -> dict:
        """Поля read-представления лицензии."""
        return {
            "id": str(instance.pk),
            "signed_at": instance.signed_at and instance.signed_at.isoformat(),
            "valid_until_year": instance.valid_until_year,
            "is_signed": instance.is_signed,
            "is_active": instance.is_active,
            "contract": {
                "id": str(instance.contract_id),
                "contract_number": instance.contract.contract_number,
            },
            "interaction_product": {
                "id": str(instance.interaction_product_id),
                "interaction": str(instance.interaction_product.interaction_id),
                "product": {
                    "id": str(instance.interaction_product.product_id),
                    "name": instance.interaction_product.product.name,
                },
            },
            "created_by": (
                {
                    "id": instance.created_by_id,
                    "email": instance.created_by.email,
                    "full_name": instance.created_by.get_full_name(),
                }
                if instance.created_by_id
                else None
            ),
        }

    def get_post_data(self) -> dict:
        """Данные создания лицензии (договор и продукт — по id)."""
        contract = ContractFactory()
        product = InteractionProductFactory(interaction=contract.interaction)
        return {
            "contract": str(contract.pk),
            "interaction_product": str(product.pk),
            "valid_until_year": 2027,
            "is_signed": True,
            "signed_at": "2026-03-01",
        }

    def get_change_data(self) -> dict:
        """Данные обновления лицензии."""
        return {"valid_until_year": 2030, "is_signed": True}

    def test_add_sets_created_by_and_active(self) -> None:
        """Создание проставляет автора из запроса и делает лицензию действующей."""
        response = self.client.post(
            path=self.list_url,
            data=self.get_post_data(),
            format="json",
        )

        # Проверяем, что лицензия создана
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        # Проверяем автора и активность
        self.assertEqual(response.data["created_by"]["id"], self.user.pk)
        self.assertTrue(response.data["is_active"])

    def test_add_supersedes_previous_active_license(self) -> None:
        """Перезаключение закрывает прежнюю лицензию и создаёт новую."""
        previous = LicenseFactory()
        data = {
            "contract": str(previous.contract_id),
            "interaction_product": str(previous.interaction_product_id),
            "valid_until_year": 2030,
        }

        response = self.client.post(path=self.list_url, data=data, format="json")
        previous.refresh_from_db()

        # Проверяем, что создана новая действующая лицензия
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertTrue(response.data["is_active"])
        # Проверяем, что прежняя закрыта, а не перезаписана
        self.assertFalse(previous.is_active)
        self.assertIsNotNone(previous.superseded_at)
        # Проверяем, что действующая лицензия для пары ровно одна
        self.assertEqual(
            License.objects.filter(
                contract=previous.contract,
                interaction_product=previous.interaction_product,
                is_active=True,
            ).count(),
            1,
        )

    def test_add_returns_400_when_product_from_another_interaction(self) -> None:
        """Продукт другого взаимодействия отклоняется (License.clean)."""
        contract = ContractFactory()
        foreign_product = InteractionProductFactory()

        response = self.client.post(
            path=self.list_url,
            data={
                "contract": str(contract.pk),
                "interaction_product": str(foreign_product.pk),
            },
            format="json",
        )

        # Проверяем, что ошибка привязана к полю interaction_product
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interaction_product", response.data)

    def test_change_returns_400_for_superseded_license(self) -> None:
        """Заменённая лицензия — запись истории, её нельзя редактировать."""
        instance = LicenseFactory(is_active=False)

        response = self.client.patch(
            path=self.detail_url(instance),
            data={"valid_until_year": 2035},
            format="json",
        )

        # Проверяем, что история версий защищена
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_returns_400_when_contract_replaced(self) -> None:
        """Договор лицензии после создания менять нельзя."""
        instance = LicenseFactory()

        response = self.client.patch(
            path=self.detail_url(instance),
            data={"contract": str(ContractFactory(interaction=instance.contract.interaction).pk)},
            format="json",
        )

        # Проверяем, что смена договора отклонена
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("contract", response.data)

    def assert_filter_returns(self, params: dict, expected: list[License]) -> None:
        """Проверяет, что список с фильтром содержит ровно ожидаемые лицензии."""
        response = self.client.get(path=self.list_url, data=params)

        # Проверяем состав выдачи (порядок не важен)
        self.assertEqual(
            sorted(item["id"] for item in response.data["results"]),
            sorted(str(license.pk) for license in expected),
        )

    def test_filter_by_interaction_ids_uses_contract_interaction(self) -> None:
        """Фильтр interaction__ids возвращает лицензии указанного взаимодействия."""
        target = LicenseFactory()
        LicenseFactory()

        self.assert_filter_returns(
            params={"interaction__ids": str(target.contract.interaction_id)},
            expected=[target],
        )

    def test_filter_by_product_ids(self) -> None:
        """Фильтр product__ids возвращает лицензии на указанный каталожный продукт."""
        target = LicenseFactory()
        LicenseFactory()

        self.assert_filter_returns(
            params={"product__ids": str(target.interaction_product.product_id)},
            expected=[target],
        )

    def test_filter_by_valid_until_year_range(self) -> None:
        """Фильтры valid_until_year__gte/__lte ограничивают срок действия."""
        inside = LicenseFactory(valid_until_year=2027)
        LicenseFactory(valid_until_year=2024)
        LicenseFactory(valid_until_year=2035)

        self.assert_filter_returns(
            params={"valid_until_year__gte": 2026, "valid_until_year__lte": 2028},
            expected=[inside],
        )

    def test_filter_by_is_active_and_is_signed(self) -> None:
        """Фильтры is_active и is_signed выбирают действующие/подписанные лицензии."""
        signed = LicenseFactory(is_signed=True)
        LicenseFactory(is_signed=False)
        superseded = LicenseFactory(is_active=False, is_signed=True)

        self.assert_filter_returns(params={"is_signed": "true", "is_active": "true"}, expected=[signed])
        self.assert_filter_returns(params={"is_active": "false"}, expected=[superseded])
