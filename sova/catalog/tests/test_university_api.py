from django.urls import reverse
from rest_framework.test import APITestCase

from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import InteractionFactory


class UniversityHasInteractionsTestCase(APITestCase):
    """Флаг has_interactions в ответах API вузов."""

    def setUp(self) -> None:
        """Аутентифицирует клиента: эндпоинты вузов закрыты для анонимов."""
        self.client.force_authenticate(user=UserFactory())

    def test_list_marks_only_universities_with_interactions(self) -> None:
        with_interaction = InteractionFactory().university
        without_interaction = UniversityFactory()

        response = self.client.get(reverse("catalog:university-list"))

        self.assertEqual(response.status_code, 200)
        flags = {item["id"]: item["has_interactions"] for item in response.json()["results"]}
        self.assertTrue(flags[str(with_interaction.id)])
        self.assertFalse(flags[str(without_interaction.id)])

    def test_retrieve_returns_the_flag(self) -> None:
        university = InteractionFactory().university

        response = self.client.get(reverse("catalog:university-detail", args=(university.id,)))

        self.assertTrue(response.json()["has_interactions"])

    def test_filter_selects_universities_with_interactions(self) -> None:
        with_interaction = InteractionFactory().university
        UniversityFactory()

        response = self.client.get(reverse("catalog:university-list"), {"has_interactions": "true"})

        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [str(with_interaction.id)])

    def test_filter_selects_universities_without_interactions(self) -> None:
        InteractionFactory()
        without_interaction = UniversityFactory()

        response = self.client.get(reverse("catalog:university-list"), {"has_interactions": "false"})

        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [str(without_interaction.id)])

    def test_created_university_has_no_interactions(self) -> None:
        """У ответа на создание аннотации вьюсета нет, флаг всё равно приходит."""
        response = self.client.post(reverse("catalog:university-list"), {"name": "Новый вуз"}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["has_interactions"])
