from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from sova.catalog.tests.factories import B2CClientFactory, UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Interaction, Responsible


class ProvisionCommandTestCase(TestCase):
    """Тесты команды provision: тестовые взаимодействия для разработки."""

    def test_creates_interactions_with_responsible(self) -> None:
        manager = UserFactory(email="kam@kam.ru")
        UniversityFactory()
        B2CClientFactory()

        call_command("provision", "--interactions", "4", stdout=StringIO())

        self.assertEqual(Interaction.objects.count(), 4)
        self.assertEqual(Interaction.objects.filter(university__isnull=False).count(), 3)
        self.assertEqual(Interaction.objects.filter(b2c_client__isnull=False).count(), 1)
        self.assertEqual(
            list(
                Interaction.objects.order_by("sequence_number").values_list(
                    "sequence_number",
                    flat=True,
                ),
            ),
            [1, 2, 3, 4],
        )
        self.assertEqual(
            Responsible.objects.filter(manager=manager, unassigned_at__isnull=True).count(),
            4,
        )

    def test_creates_ten_interactions_by_default(self) -> None:
        UserFactory(email="kam@kam.ru")
        UniversityFactory()

        call_command("provision", stdout=StringIO())

        self.assertEqual(Interaction.objects.count(), 10)

    def test_repeated_run_tops_up_to_the_requested_count(self) -> None:
        UserFactory(email="kam@kam.ru")
        UniversityFactory()

        call_command("provision", "--interactions", "3", stdout=StringIO())
        call_command("provision", "--interactions", "5", stdout=StringIO())

        self.assertEqual(Interaction.objects.count(), 5)

    def test_all_interactions_are_with_universities_without_b2c_clients(self) -> None:
        UserFactory(email="kam@kam.ru")
        UniversityFactory()

        call_command("provision", "--interactions", "4", stdout=StringIO())

        self.assertEqual(Interaction.objects.filter(university__isnull=False).count(), 4)

    def test_falls_back_to_any_active_user_as_responsible(self) -> None:
        """Ответственным становится первый активный пользователь, если КАМа по почте нет."""
        manager = UserFactory(email="other@example.com")
        UniversityFactory()

        call_command("provision", "--interactions", "2", stdout=StringIO())

        self.assertEqual(Responsible.objects.filter(manager=manager).count(), 2)

    def test_without_universities_raises(self) -> None:
        UserFactory(email="kam@kam.ru")

        with self.assertRaises(CommandError):
            call_command("provision", stdout=StringIO())

    def test_without_users_raises(self) -> None:
        UniversityFactory()

        with self.assertRaises(CommandError):
            call_command("provision", stdout=StringIO())

    def test_zero_count_raises(self) -> None:
        with self.assertRaises(CommandError):
            call_command("provision", "--interactions", "0", stdout=StringIO())
