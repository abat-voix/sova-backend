from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.tests.factories import OrganizationFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import ContractFile, Responsible
from sova.interactions.tests.factories import ContractFactory, InteractionFactory


class HeadlessContractVisibilityApiTestCase(APITestCase):
    """Headless-договор виден по его ответственным — тем же правилом, что взаимодействие."""

    list_url = reverse("interactions:contract-list")
    files_url = reverse("interactions:contract-file-list")

    @staticmethod
    def create_user(role: str | None = None):
        user = UserFactory()
        if role is not None:
            UserRole.objects.create(user=user, role=role)
        return user

    @staticmethod
    def create_contract(*managers):
        contract = ContractFactory(interaction=None, organization=OrganizationFactory())
        for manager in managers:
            Responsible.objects.create(contract=contract, manager=manager)
        return contract

    def visible_ids(self, user, url=None) -> set[str]:
        self.client.force_authenticate(user=user)
        response = self.client.get(url or self.list_url)
        return {str(item["id"]) for item in response.data["results"]}

    def test_kam_sees_own_and_unassigned_but_not_foreign(self) -> None:
        kam = self.create_user(SystemRole.KAM)
        own = self.create_contract(kam)
        unassigned = self.create_contract()
        self.create_contract(self.create_user(SystemRole.KAM))

        # Проверяем выборку КАМа
        self.assertEqual(self.visible_ids(kam), {str(own.pk), str(unassigned.pk)})

    def test_head_sees_contracts_of_kams(self) -> None:
        head = self.create_user(SystemRole.HEAD)
        of_kam = self.create_contract(self.create_user(SystemRole.KAM))
        self.create_contract(self.create_user(SystemRole.HEAD))

        # Проверяем, что руководитель видит договор КАМа и не видит договор другого руководителя
        self.assertEqual(self.visible_ids(head), {str(of_kam.pk)})

    def test_admin_sees_all(self) -> None:
        contracts = {str(self.create_contract(self.create_user(SystemRole.KAM)).pk), str(self.create_contract().pk)}

        # Проверяем, что администратор видит все договоры
        self.assertEqual(self.visible_ids(self.create_user(SystemRole.PLATFORM_ADMIN)), contracts)

    def test_headless_contract_shows_own_counterparty(self) -> None:
        contract = self.create_contract()
        self.client.force_authenticate(user=self.create_user(SystemRole.PLATFORM_ADMIN))
        item = self.client.get(self.list_url).data["results"][0]

        # Проверяем, что у договора без взаимодействия контрагент берётся из самого договора
        self.assertIsNone(item["interaction"])
        self.assertEqual(item["organization"]["id"], str(contract.organization.pk))
        self.assertIsNone(item["b2c_client"])

    def test_user_without_role_sees_nothing(self) -> None:
        self.create_contract()
        self.client.force_authenticate(user=self.create_user())

        # Пользователь без прикладной роли не входит в бизнес-разделы.
        self.assertEqual(self.client.get(self.list_url).status_code, 403)

    def test_files_of_foreign_contract_are_hidden(self) -> None:
        kam = self.create_user(SystemRole.KAM)
        own_file = ContractFile.objects.create(contract=self.create_contract(kam), file="contracts/a.pdf")
        ContractFile.objects.create(
            contract=self.create_contract(self.create_user(SystemRole.KAM)), file="contracts/b.pdf"
        )

        # Проверяем журнал файлов: только файл своего договора
        self.assertEqual(self.visible_ids(kam, url=self.files_url), {str(own_file.pk)})

    def test_kam_attach_assigns_the_kam(self) -> None:
        """КАМ создаёт взаимодействие из своего договора реестра — ответственный только он, коллега из реестра — нет."""
        kam = self.create_user(SystemRole.KAM)
        colleague = self.create_user(SystemRole.KAM)
        contract = self.create_contract(kam, colleague)
        self.client.force_authenticate(user=kam)

        response = self.client.post(reverse("interactions:contract-attach-to-new-interaction", args=[contract.pk]))

        # Проверяем ответ и ответственных нового взаимодействия
        self.assertEqual(response.status_code, 200)
        current = Responsible.objects.filter(
            interaction_id=response.data["interaction"]["id"], unassigned_at__isnull=True
        ).values_list("manager_id", flat=True)
        self.assertEqual(list(current), [kam.pk])

    def test_patch_cannot_attach_headless_contract(self) -> None:
        """Привязка headless-договора только через attach-to-new-interaction: PATCH interaction отклоняется."""
        kam = self.create_user(SystemRole.KAM)
        contract = self.create_contract(kam)
        interaction = InteractionFactory(organization=contract.organization)
        self.client.force_authenticate(user=kam)

        response = self.client.patch(
            reverse("interactions:contract-detail", args=[contract.pk]),
            data={"interaction": str(interaction.pk)},
            format="json",
        )

        # Проверяем ошибку по полю и то, что договор остался headless
        self.assertEqual(response.status_code, 400)
        self.assertIn("interaction", response.data)
        contract.refresh_from_db()
        self.assertIsNone(contract.interaction_id)
