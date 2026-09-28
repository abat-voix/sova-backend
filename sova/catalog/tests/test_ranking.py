from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.services import catalog_ranking_service
from sova.catalog.tests.factories import (
    B2CClientFactory,
    DirectionFactory,
    ProductFactory,
    ProgramFactory,
    OrganizationFactory,
)
from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import (
    InteractionFactory,
    InteractionProductFactory,
    InteractionProgramFactory,
)
from sova.training.enum import TrainingApplicationStatus
from sova.training.tests.factories import (
    LearnerFactory,
    TrainingApplicationFactory,
    TrainingApplicationLearnerFactory,
    TrainingStreamFactory,
)


def enroll(stream, learner=None, is_paid=True, application=None):
    """Участник заявки на поток; по умолчанию оплатил, то есть зачислен."""
    return TrainingApplicationLearnerFactory(
        application=application or TrainingApplicationFactory(stream=stream),
        learner=learner or LearnerFactory(),
        is_paid=is_paid,
    )


def stream_for(organization=None, b2c_client=None, program=None):
    """Поток по программе взаимодействия с контрагентом."""
    interaction = InteractionFactory(organization=organization, b2c_client=b2c_client)
    interaction_program = InteractionProgramFactory(interaction=interaction, program=program or ProgramFactory())
    return TrainingStreamFactory(interaction_program=interaction_program)


class CompetitionRanksTestCase(SimpleTestCase):
    """Спортивные места: при равенстве место делится, следующее пропускается."""

    def test_ties_share_place_and_skip_next(self) -> None:
        ranks = catalog_ranking_service.competition_ranks({"a": 5, "b": 3, "c": 3, "d": 1})

        self.assertEqual(ranks, {"a": 1, "b": 2, "c": 2, "d": 4})

    def test_empty(self) -> None:
        self.assertEqual(catalog_ranking_service.competition_ranks({}), {})


class RankingApiTestCase(APITestCase):
    """Место в рейтинге в списках каталога."""

    def setUp(self) -> None:
        user = UserFactory()
        UserRole.objects.create(user=user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=user)

    def ranks(self, url_name: str, params: dict | None = None) -> dict:
        response = self.client.get(reverse(url_name), params or {})
        self.assertEqual(response.status_code, 200, response.data)
        return {item["id"]: item["rank"] for item in response.json()["results"]}

    def test_organizations_ranked_by_enrolled_people(self) -> None:
        first, second, tied, unranked = (OrganizationFactory() for _ in range(4))
        first_stream = stream_for(organization=first)
        learner = LearnerFactory()
        enroll(first_stream, learner=learner)
        enroll(first_stream)
        # Тот же человек на другом потоке того же вуза считается один раз
        enroll(stream_for(organization=first), learner=learner)
        enroll(stream_for(organization=second))
        enroll(stream_for(organization=tied))
        # Не оплатили или заявка отменена — не зачислены
        enroll(stream_for(organization=unranked), is_paid=False)
        cancelled = TrainingApplicationFactory(
            stream=stream_for(organization=unranked),
            status=TrainingApplicationStatus.CANCELLED,
        )
        enroll(cancelled.stream, application=cancelled)

        ranks = self.ranks("catalog:organization-list")

        self.assertEqual(ranks[str(first.id)], 1)
        self.assertEqual(ranks[str(second.id)], 2)
        self.assertEqual(ranks[str(tied.id)], 2)
        self.assertIsNone(ranks[str(unranked.id)])

    def test_rank_does_not_depend_on_list_filters(self) -> None:
        leader, runner_up = OrganizationFactory(), OrganizationFactory(name="Второй вуз")
        enroll(stream_for(organization=leader))
        enroll(stream_for(organization=leader))
        enroll(stream_for(organization=runner_up))

        ranks = self.ranks("catalog:organization-list", {"search": "Второй вуз"})

        self.assertEqual(ranks, {str(runner_up.id): 2})

    def test_filters_and_ordering_by_rank(self) -> None:
        leader, runner_up, unranked = OrganizationFactory(), OrganizationFactory(), OrganizationFactory()
        enroll(stream_for(organization=leader))
        enroll(stream_for(organization=leader))
        enroll(stream_for(organization=runner_up))

        top = self.ranks("catalog:organization-list", {"rank_max": 1})
        ranked = self.ranks("catalog:organization-list", {"has_rank": "true", "ordering": "rank"})
        without_rank = self.ranks("catalog:organization-list", {"has_rank": "false"})

        self.assertEqual(top, {str(leader.id): 1})
        self.assertEqual(list(ranked), [str(leader.id), str(runner_up.id)])
        self.assertEqual(without_rank, {str(unranked.id): None})

    def test_b2c_clients_ranked(self) -> None:
        leader, runner_up = B2CClientFactory(), B2CClientFactory()
        enroll(stream_for(b2c_client=leader))
        enroll(stream_for(b2c_client=leader))
        enroll(stream_for(b2c_client=runner_up))

        ranks = self.ranks("catalog:b2c-client-list")

        self.assertEqual(ranks, {str(leader.id): 1, str(runner_up.id): 2})

    def test_programs_and_directions_ranked(self) -> None:
        leading_direction, other_direction = DirectionFactory(), DirectionFactory()
        leading_program = ProgramFactory(direction=leading_direction)
        other_program = ProgramFactory(direction=leading_direction)
        third_program = ProgramFactory(direction=other_direction)
        enroll(stream_for(organization=OrganizationFactory(), program=leading_program))
        enroll(stream_for(organization=OrganizationFactory(), program=leading_program))
        enroll(stream_for(organization=OrganizationFactory(), program=other_program))
        enroll(stream_for(organization=OrganizationFactory(), program=third_program))

        programs = self.ranks("catalog:program-list")
        directions = self.ranks("catalog:direction-list")

        self.assertEqual(programs[str(leading_program.id)], 1)
        self.assertEqual(programs[str(other_program.id)], 2)
        self.assertEqual(programs[str(third_program.id)], 2)
        self.assertEqual(directions, {str(leading_direction.id): 1, str(other_direction.id): 2})

    def test_products_ranked_by_active_interactions(self) -> None:
        leader, runner_up, inactive = ProductFactory(), ProductFactory(), ProductFactory()
        InteractionProductFactory(product=leader)
        InteractionProductFactory(product=leader)
        InteractionProductFactory(product=runner_up)
        InteractionProductFactory(product=inactive, is_active=False)

        ranks = self.ranks("catalog:product-list")

        self.assertEqual(ranks, {str(leader.id): 1, str(runner_up.id): 2, str(inactive.id): None})

    def test_retrieve_and_create_return_rank(self) -> None:
        organization = OrganizationFactory()
        enroll(stream_for(organization=organization))

        retrieved = self.client.get(reverse("catalog:organization-detail", args=(organization.id,)))
        created = self.client.post(reverse("catalog:direction-list"), {"name": "Новое направление"}, format="json")

        self.assertEqual(retrieved.json()["rank"], 1)
        self.assertEqual(created.status_code, 201, created.data)
        self.assertIsNone(created.json()["rank"])
