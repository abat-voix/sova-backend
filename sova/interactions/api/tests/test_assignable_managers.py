from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Supervision, SystemRole, UserRole
from sova.catalog.tests.factories import UniversityFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.services import responsible_service
from sova.interactions.services.contract_attachment import contract_attachment_service
from sova.interactions.tests.factories import ContractFactory


def create_user(role: str, last_name: str):
    """Создаёт пользователя с ролью СОВА; фамилия задаёт порядок в выдаче."""
    user = UserFactory(last_name=last_name)
    UserRole.objects.create(user=user, role=role)
    return user


class AssignableManagersApiTestCase(APITestCase):
    """GET /api/interactions/interactions/{id}/assignable-managers/ — кандидаты с КАМами из реестра."""

    def setUp(self) -> None:
        """Взаимодействие из договора реестра с КАМами своей и чужой команды руководителя."""
        self.head = create_user(SystemRole.HEAD, "Гусев")
        self.mine = create_user(SystemRole.KAM, "Андреев")
        self.foreign = create_user(SystemRole.KAM, "Борисов")
        self.free = create_user(SystemRole.KAM, "Васильев")
        Supervision.objects.create(kam=self.mine, head=self.head)
        Supervision.objects.create(kam=self.foreign, head=create_user(SystemRole.HEAD, "Другой"))

        contract = ContractFactory(interaction=None, university=UniversityFactory())
        responsible_service.sync_contract_responsibles(
            contract=contract, managers=[self.foreign, self.mine], assigned_by=None
        )
        self.interaction = contract_attachment_service.attach_to_new_interaction(contract=contract, author=self.head)

    def get(self, user) -> list[tuple]:
        self.client.force_authenticate(user=user)
        response = self.client.get(
            reverse("interactions:interaction-assignable-managers", args=[self.interaction.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        return [
            (item["manager"]["id"], item["from_registry"], item["assignable"], item["is_responsible"])
            for item in response.data
        ]

    def test_head_sees_registry_kams_first_foreign_one_not_assignable(self) -> None:
        responsible_service.assign(interaction=self.interaction, manager=self.mine, assigned_by=self.head)

        # Проверяем: сначала КАМы реестра (чужой — недоступен), затем свободный КАМ и сам руководитель
        self.assertEqual(
            self.get(self.head),
            [
                (self.mine.pk, True, True, True),
                (self.foreign.pk, True, False, False),
                (self.free.pk, False, True, False),
                (self.head.pk, False, True, False),
            ],
        )

    def test_kam_sees_only_self_without_registry(self) -> None:
        # Проверяем: КАМу подсказка реестра не показывается, назначить он может только себя
        self.assertEqual(self.get(self.free), [(self.free.pk, False, True, False)])

    def test_admin_sees_registry_kams(self) -> None:
        admin = create_user(SystemRole.PLATFORM_ADMIN, "Админов")

        # Проверяем: администратору КАМы реестра показаны первыми и доступны
        self.assertEqual(
            self.get(admin)[:2],
            [(self.mine.pk, True, True, False), (self.foreign.pk, True, True, False)],
        )

    def test_interaction_without_contracts_has_no_registry_kams(self) -> None:
        self.interaction = contract_attachment_service.attach_to_new_interaction(
            contract=ContractFactory(interaction=None, university=UniversityFactory()), author=self.head
        )

        # Проверяем: без КАМов реестра — только те, кого руководитель может назначить
        self.assertEqual(
            self.get(self.head),
            [(self.mine.pk, False, True, False), (self.free.pk, False, True, False), (self.head.pk, False, True, False)],
        )
