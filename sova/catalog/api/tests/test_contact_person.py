from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.models import ContactPerson, UniversityContact
from sova.catalog.tests.factories import (
    B2CClientContactFactory,
    ContactPersonFactory,
    ProductFactory,
    UniversityContactFactory,
    UniversityFactory,
    VendorContactFactory,
    VendorFactory,
)
from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.interactions.models import InteractionContact
from sova.interactions.tests.factories import InteractionFactory


class ContactPersonApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/catalog/contact-persons/."""

    url_basename = "catalog:contact-person"
    model = ContactPerson

    def create_instance(self, **kwargs) -> ContactPerson:
        """Создаёт контактное лицо со связью с вузом."""
        return UniversityContactFactory(contact=ContactPersonFactory(**kwargs), position="Проректор").contact

    def get_expected_data(self, instance: ContactPerson) -> dict:
        """Поля read-представления: человек и его связи."""
        return {
            "id": str(instance.pk),
            "full_name": instance.full_name,
            "email": instance.email,
            "phone": instance.phone,
            "telegram": instance.telegram,
            "is_active": instance.is_active,
            "affiliations": [
                {
                    "id": str(link.pk),
                    "type": "university",
                    "organization": {"id": str(link.university_id), "name": link.university.name},
                    "position": link.position,
                    "preferred_channels": link.preferred_channels,
                    "products": [],
                }
                for link in instance.university_links.all()
            ],
        }

    def get_post_data(self) -> dict:
        """Данные создания человека."""
        return {"full_name": "Петров Пётр", "telegram": "@petrov_pp"}

    def get_change_data(self) -> dict:
        """Данные обновления человека."""
        return {"phone": "+7 900 000-00-00"}

    def get_search_term(self, instance: ContactPerson) -> str:
        """Поиск по ФИО."""
        return instance.full_name

    def test_telegram_is_normalized(self) -> None:
        """Ник Telegram сохраняется без @ и ссылки."""
        response = self.client.post(
            path=self.list_url,
            data={"full_name": "Сидоров", "telegram": "https://t.me/Sidorov_S"},
            format="json",
        )

        # Проверяем нормализацию ника
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["telegram"], "Sidorov_S")

    def test_invalid_telegram_returns_400(self) -> None:
        """Недопустимый ник Telegram — 400 по полю telegram."""
        response = self.client.post(path=self.list_url, data={"full_name": "Сидоров", "telegram": "ab"}, format="json")

        # Проверяем ошибку поля
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("telegram", response.data)

    def test_person_with_several_affiliations(self) -> None:
        """В ответе все связи человека: разные организации — разные должности."""
        contact = ContactPersonFactory()
        UniversityContactFactory(contact=contact, position="Проректор")
        product = ProductFactory()
        VendorContactFactory(contact=contact, vendor=product.vendor, position="Консультант", products=[product])

        response = self.client.get(path=self.detail_url(contact))

        # Проверяем типы, должности и продукты связей
        affiliations = {item["type"]: item for item in response.data["affiliations"]}
        self.assertEqual(affiliations["university"]["position"], "Проректор")
        self.assertEqual(affiliations["vendor"]["position"], "Консультант")
        self.assertEqual(affiliations["vendor"]["products"], [{"id": str(product.pk), "name": product.name}])

    def test_filters_by_organizations_without_duplicates(self) -> None:
        """Фильтры по вузам, B2C-клиентам, вендорам и продуктам; человек с двумя подходящими связями — один раз."""
        contact = ContactPersonFactory()
        first = UniversityContactFactory(contact=contact).university
        second = UniversityContactFactory(contact=contact).university
        client_link = B2CClientContactFactory()
        product = ProductFactory()
        vendor_link = VendorContactFactory(vendor=product.vendor, products=[product])
        UniversityContactFactory()

        cases = {
            "university__ids": (f"{first.pk},{second.pk}", contact),
            "b2c_client__ids": (str(client_link.b2c_client_id), client_link.contact),
            "vendor__ids": (str(vendor_link.vendor_id), vendor_link.contact),
            "product__ids": (str(product.pk), vendor_link.contact),
        }
        for param, (value, expected) in cases.items():
            with self.subTest(param=param):
                response = self.client.get(path=self.list_url, data={param: value})

                self.assertEqual([item["id"] for item in response.data["results"]], [str(expected.pk)])

    def test_search_by_position(self) -> None:
        """Поиск находит человека по должности в любой из связей."""
        target = VendorContactFactory(position="Архитектор решений").contact
        UniversityContactFactory(position="Проректор")

        response = self.client.get(path=self.list_url, data={"search": "Архитектор"})

        # Проверяем, что найден только человек с такой должностью
        self.assertEqual([item["id"] for item in response.data["results"]], [str(target.pk)])

    def test_delete_removes_affiliations(self) -> None:
        """Удаление человека удаляет и его связи."""
        link = UniversityContactFactory()

        response = self.client.delete(path=self.detail_url(link.contact))

        # Проверяем, что связи удалены вместе с человеком
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(UniversityContact.objects.exists())

    def test_delete_linked_to_interaction_returns_409(self) -> None:
        """Человек, привязанный к идущему взаимодействию, не удаляется."""
        link = UniversityContactFactory()
        interaction = InteractionFactory(university=link.university)
        InteractionContact.objects.create(interaction=interaction, contact_person=link.contact)

        response = self.client.delete(path=self.detail_url(link.contact))

        # Проверяем конфликт и что ничего не удалено
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(UniversityContact.objects.exists())


class PossibleDuplicatesApiTestCase(APITestCase):
    """Тесты GET /api/catalog/contact-persons/possible-duplicates/."""

    def setUp(self) -> None:
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=user)
        self.url = reverse("catalog:contact-person-possible-duplicates")

    def test_returns_namesakes_with_affiliations(self) -> None:
        """Тёзки из других организаций показываются со связями — «это он?»."""
        link = UniversityContactFactory(contact__full_name="Иванов Иван", position="Проректор")
        ContactPersonFactory(full_name="Петров Пётр")

        response = self.client.get(path=self.url, data={"full_name": "иванов иван"})

        # Проверяем кандидата и его должность в вузе
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in response.data], [str(link.contact_id)])
        self.assertEqual(response.data[0]["affiliations"][0]["position"], "Проректор")

    def test_excludes_itself_and_matches_phone(self) -> None:
        """Сам контакт исключается; телефон сравнивается без учёта формата."""
        itself = ContactPersonFactory(full_name="Иванов Иван", phone="+7 (900) 111-22-33")
        other = ContactPersonFactory(full_name="Иван Иванов", phone="89001112233")

        response = self.client.get(
            path=self.url,
            data={"full_name": "Иванов Иван", "phone": "+79001112233", "exclude": str(itself.pk)},
        )

        # Проверяем, что найден только другой человек с тем же телефоном
        self.assertEqual([item["id"] for item in response.data], [str(other.pk)])


class ContactAffiliationApiTestCase(APITestCase):
    """Тесты /api/catalog/university-contacts/ и /api/catalog/vendor-contacts/."""

    def setUp(self) -> None:
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=user)

    def test_create_university_contact(self) -> None:
        """Связь создаётся с должностью и способами связи."""
        contact = ContactPersonFactory()
        university = UniversityFactory()

        response = self.client.post(
            path=reverse("catalog:university-contact-list"),
            data={
                "contact": str(contact.pk),
                "university": str(university.pk),
                "position": "Проректор",
                "preferred_channels": ["email", "telegram"],
            },
            format="json",
        )

        # Проверяем ответ read-сериализатором
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        self.assertEqual(response.data["university"]["id"], str(university.pk))
        self.assertEqual(response.data["preferred_channels"], ["email", "telegram"])

    def test_duplicate_pair_returns_400(self) -> None:
        """Повтор пары «человек + вуз» — 400."""
        link = UniversityContactFactory()

        response = self.client.post(
            path=reverse("catalog:university-contact-list"),
            data={"contact": str(link.contact_id), "university": str(link.university_id)},
            format="json",
        )

        # Проверяем, что ограничение уникальности не доходит до БД
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organization_cannot_be_changed(self) -> None:
        """Сменить организацию связи нельзя — это другая связь."""
        link = UniversityContactFactory()

        response = self.client.patch(
            path=reverse("catalog:university-contact-detail", args=[link.pk]),
            data={"university": str(UniversityFactory().pk)},
            format="json",
        )

        # Проверяем ошибку по полю university
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("university", response.data)

    def test_vendor_contact_rejects_foreign_products(self) -> None:
        """Продукты связи с вендором — только продукты этого вендора."""
        vendor = VendorFactory()

        response = self.client.post(
            path=reverse("catalog:vendor-contact-list"),
            data={
                "contact": str(ContactPersonFactory().pk),
                "vendor": str(vendor.pk),
                "products": [str(ProductFactory().pk)],
            },
            format="json",
        )

        # Проверяем ошибку по полю products
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("products", response.data)

    def test_delete_used_affiliation_unlinks(self) -> None:
        """Удаление связи — уход из организации: человек отвязывается от активного взаимодействия вуза."""
        link = UniversityContactFactory()
        interaction = InteractionFactory(university=link.university)
        InteractionContact.objects.create(interaction=interaction, contact_person=link.contact)

        response = self.client.delete(path=reverse("catalog:university-contact-detail", args=[link.pk]))

        # Проверяем удаление и отвязку
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(UniversityContact.objects.exists())
        self.assertFalse(InteractionContact.objects.filter(unlinked_at__isnull=True).exists())


class ContactObserverApiTestCase(APITestCase):
    """Наблюдатель читает контактные лица и их связи, но не меняет их."""

    def setUp(self) -> None:
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.OBSERVER)
        self.client.force_authenticate(user=user)

    def test_observer_reads_contacts_and_affiliations(self) -> None:
        """Список людей, связей и поиск дублей доступны наблюдателю."""
        UniversityContactFactory()

        responses = [
            self.client.get(path=reverse("catalog:contact-person-list")),
            self.client.get(path=reverse("catalog:university-contact-list")),
            self.client.get(path=reverse("catalog:contact-person-possible-duplicates"), data={"full_name": "Иванов"}),
        ]

        # Проверяем, что все запросы на чтение разрешены
        self.assertEqual([response.status_code for response in responses], [status.HTTP_200_OK] * 3)

    def test_observer_cannot_change_contacts_and_affiliations(self) -> None:
        """Создание и удаление людей и связей наблюдателю запрещены."""
        link = UniversityContactFactory()

        responses = [
            self.client.post(path=reverse("catalog:contact-person-list"), data={"full_name": "Петров Пётр"}),
            self.client.delete(path=reverse("catalog:contact-person-detail", args=[link.contact_id])),
            self.client.delete(path=reverse("catalog:university-contact-detail", args=[link.pk])),
        ]

        # Проверяем запрет и что связь осталась
        self.assertEqual([response.status_code for response in responses], [status.HTTP_403_FORBIDDEN] * 3)
        self.assertTrue(UniversityContact.objects.filter(pk=link.pk).exists())
