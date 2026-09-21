from rest_framework import status
from rest_framework.test import APITestCase

from sova.catalog.models import ContactPerson
from sova.catalog.tests.factories import (
    B2CClientFactory,
    ContactPersonFactory,
    UniversityFactory,
)
from sova.core.tests.base import BaseApiTestMixin


class ContactPersonApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/contact-persons/."""

    url_basename = "catalog:contact-person"
    model = ContactPerson

    def create_instance(self, **kwargs) -> ContactPerson:
        """Создаёт контактное лицо вуза."""
        return ContactPersonFactory(**kwargs)

    def get_expected_data(self, instance: ContactPerson) -> dict:
        """Поля read-представления контактного лица."""
        university = instance.university
        return {
            "id": str(instance.pk),
            "full_name": instance.full_name,
            "position": instance.position,
            "email": instance.email,
            "phone": instance.phone,
            "is_active": instance.is_active,
            "university": (
                {"id": str(university.pk), "name": university.name}
                if university
                else None
            ),
            "b2c_client": None,
        }

    def get_post_data(self) -> dict:
        """Данные создания контактного лица вуза."""
        return {
            "full_name": "Петров Пётр",
            "position": "Проректор",
            "university": str(UniversityFactory().pk),
        }

    def get_change_data(self) -> dict:
        """Данные обновления контактного лица."""
        return {"position": "Декан", "phone": "+7 900 000-00-00"}

    def get_search_term(self, instance: ContactPerson) -> str:
        """Поиск по ФИО."""
        return instance.full_name

    def test_add_for_b2c_client_creates_contact(self) -> None:
        """Контактное лицо B2C-клиента создаётся без вуза."""
        client = B2CClientFactory()

        response = self.client.post(
            path=self.list_url,
            data={"full_name": "Сидоров", "b2c_client": str(client.pk)},
            format="json",
        )

        # Проверяем, что контрагентом выбран клиент, а вуз пуст
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertIsNone(response.data["university"])
        self.assertEqual(response.data["b2c_client"]["id"], str(client.pk))

    def test_add_returns_400_without_counterparty(self) -> None:
        """Создание без вуза и без клиента возвращает 400."""
        response = self.client.post(
            path=self.list_url,
            data={"full_name": "Без контрагента"},
            format="json",
        )

        # Проверяем, что CheckConstraint не доходит до БД
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_with_both_counterparties(self) -> None:
        """Создание одновременно с вузом и клиентом возвращает 400."""
        response = self.client.post(
            path=self.list_url,
            data={
                "full_name": "Двойной",
                "university": str(UniversityFactory().pk),
                "b2c_client": str(B2CClientFactory().pk),
            },
            format="json",
        )

        # Проверяем, что контрагент должен быть ровно один
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_returns_400_when_adding_second_counterparty(self) -> None:
        """PATCH, добавляющий клиента к контакту вуза, возвращает 400."""
        instance = ContactPersonFactory()

        response = self.client.patch(
            path=self.detail_url(instance),
            data={"b2c_client": str(B2CClientFactory().pk)},
            format="json",
        )

        # Проверяем, что при частичном обновлении учитывается текущий контрагент
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_returns_400_with_duplicate_name_in_university(self) -> None:
        """Повтор ФИО в одном вузе возвращает 400."""
        existing = ContactPersonFactory(full_name="Дубль")

        response = self.client.post(
            path=self.list_url,
            data={"full_name": "Дубль", "university": str(existing.university_id)},
            format="json",
        )

        # Проверяем, что нарушение unique_university_contact_name отдано как 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_university_ids_returns_only_matching(self) -> None:
        """Фильтр university__ids возвращает контакты указанных вузов."""
        target = ContactPersonFactory()
        ContactPersonFactory()

        response = self.client.get(
            path=self.list_url,
            data={"university__ids": str(target.university_id)},
        )

        # Проверяем, что найден только контакт выбранного вуза
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_by_b2c_client_ids_returns_only_matching(self) -> None:
        """Фильтр b2c_client__ids возвращает контакты указанных клиентов."""
        client = B2CClientFactory()
        target = ContactPersonFactory(university=None, b2c_client=client)
        ContactPersonFactory()

        response = self.client.get(
            path=self.list_url,
            data={"b2c_client__ids": str(client.pk)},
        )

        # Проверяем, что найден только контакт выбранного клиента
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )
