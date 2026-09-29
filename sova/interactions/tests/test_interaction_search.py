from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.tests.factories import InteractionFactory


class InteractionSearchApiTestCase(APITestCase):
    """Тесты /api/interactions/interactions/?search= — поиск по контрагенту и действующему ответственному."""

    list_url = reverse("interactions:interaction-list")

    def setUp(self) -> None:
        admin = UserFactory()
        UserRole.objects.create(user=admin, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=admin)

        self.petrov = UserFactory(first_name="Пётр", last_name="Петров", email="petrov@sova.ru")
        self.sidorov = UserFactory(first_name="Иван", last_name="Сидоров", email="sidorov@sova.ru")
        self.petrov_interaction = InteractionFactory(organization=OrganizationFactory(name="МГУ"))
        self.sidorov_interaction = InteractionFactory(organization=OrganizationFactory(name="СПбГУ"))
        responsible_service.assign(interaction=self.petrov_interaction, manager=self.petrov, assigned_by=None)
        responsible_service.assign(interaction=self.sidorov_interaction, manager=self.sidorov, assigned_by=None)

    def search_ids(self, search: str) -> list[str]:
        """Идентификаторы взаимодействий, найденных по строке поиска."""
        response = self.client.get(path=self.list_url, data={"search": search})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [item["id"] for item in response.data["results"]]

    def test_search_by_responsible_last_name(self) -> None:
        """Фамилия действующего ответственного находит его взаимодействие."""
        self.assertEqual(self.search_ids("петров"), [str(self.petrov_interaction.pk)])

    def test_search_by_responsible_full_name(self) -> None:
        """Имя и фамилия вместе: каждое слово ищется отдельно, оба должны совпасть."""
        self.assertEqual(self.search_ids("Пётр Петров"), [str(self.petrov_interaction.pk)])
        # Проверяем, что имя одного и фамилия другого ничего не находят
        self.assertEqual(self.search_ids("Иван Петров"), [])

    def test_search_by_responsible_email(self) -> None:
        """Email действующего ответственного тоже участвует в поиске."""
        self.assertEqual(self.search_ids("sidorov@"), [str(self.sidorov_interaction.pk)])

    def test_search_combines_counterparty_and_responsible(self) -> None:
        """Слова запроса могут совпадать с разными полями: организация и ответственный."""
        self.assertEqual(self.search_ids("МГУ Петров"), [str(self.petrov_interaction.pk)])

    def test_unassigned_responsible_is_not_found(self) -> None:
        """Снятый с назначения ответственный в поиске не учитывается."""
        responsible_service.unassign(interaction=self.petrov_interaction, manager=self.petrov)

        self.assertEqual(self.search_ids("Петров"), [])

    def test_several_responsibles_do_not_duplicate_rows(self) -> None:
        """Два подходящих ответственных у одного взаимодействия не задваивают его в выдаче."""
        responsible_service.assign(
            interaction=self.petrov_interaction,
            manager=UserFactory(first_name="Пётр", last_name="Петровский"),
            assigned_by=None,
        )

        self.assertEqual(self.search_ids("Петров"), [str(self.petrov_interaction.pk)])
