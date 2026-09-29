from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import InteractionFactory


class OrganizationHasInteractionsTestCase(APITestCase):
    """Флаг has_interactions в ответах API вузов."""

    def setUp(self) -> None:
        """Аутентифицирует клиента: эндпоинты вузов закрыты для анонимов."""
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=user)

    def test_list_marks_only_organizations_with_interactions(self) -> None:
        with_interaction = InteractionFactory().organization
        without_interaction = OrganizationFactory()

        response = self.client.get(reverse("catalog:organization-list"))

        self.assertEqual(response.status_code, 200)
        flags = {item["id"]: item["has_interactions"] for item in response.json()["results"]}
        self.assertTrue(flags[str(with_interaction.id)])
        self.assertFalse(flags[str(without_interaction.id)])

    def test_retrieve_returns_the_flag(self) -> None:
        organization = InteractionFactory().organization

        response = self.client.get(reverse("catalog:organization-detail", args=(organization.id,)))

        self.assertTrue(response.json()["has_interactions"])

    def test_map_point_carries_the_flag(self) -> None:
        """Точка карты несёт флаг: по нему на карте видно вузы со взаимодействиями."""
        with_interaction = InteractionFactory(
            organization=OrganizationFactory(lat="55.755814", lon="37.617635"),
        ).organization
        without_interaction = OrganizationFactory(lat="59.939095", lon="30.315868")

        response = self.client.get(reverse("catalog:organization-map-points"))

        flags = {item["id"]: item["has_interactions"] for item in response.json()}
        self.assertTrue(flags[str(with_interaction.id)])
        self.assertFalse(flags[str(without_interaction.id)])

    def test_filter_selects_organizations_with_interactions(self) -> None:
        with_interaction = InteractionFactory().organization
        OrganizationFactory()

        response = self.client.get(reverse("catalog:organization-list"), {"has_interactions": "true"})

        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [str(with_interaction.id)])

    def test_filter_selects_organizations_without_interactions(self) -> None:
        InteractionFactory()
        without_interaction = OrganizationFactory()

        response = self.client.get(reverse("catalog:organization-list"), {"has_interactions": "false"})

        ids = [item["id"] for item in response.json()["results"]]
        self.assertEqual(ids, [str(without_interaction.id)])

    def test_created_organization_has_no_interactions(self) -> None:
        """У ответа на создание аннотации вьюсета нет, флаг всё равно приходит."""
        response = self.client.post(reverse("catalog:organization-list"), {"name": "Новый вуз"}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["has_interactions"])


class OrganizationInnValidationTestCase(APITestCase):
    """ИНН организации: понятное сообщение об ошибке."""

    def setUp(self) -> None:
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=user)

    def test_create_rejects_too_long_inn_with_single_message(self) -> None:
        """Слишком длинный ИНН — одно понятное сообщение, без стандартного «не более 12 символов»."""
        response = self.client.post(
            reverse("catalog:organization-list"),
            {"name": "Новый вуз", "inn": "1234567890123"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["inn"], ["ИНН должен состоять из 10 или 12 цифр."])
