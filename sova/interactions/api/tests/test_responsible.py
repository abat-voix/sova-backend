from datetime import datetime, timezone

from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.core.tests.factories import UserFactory
from sova.interactions.models import Responsible
from sova.interactions.tests.factories import InteractionFactory, ResponsibleFactory


class ResponsibleApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты чтения истории назначений /api/interactions/responsibles/."""

    url_basename = "interactions:responsible"
    model = Responsible
    allow_create = False
    allow_update = False
    allow_delete = False

    def create_instance(self, **kwargs) -> Responsible:
        """Создаёт назначение ответственного."""
        return ResponsibleFactory(**kwargs)

    def get_expected_data(self, instance: Responsible) -> dict:
        """Поля read-представления назначения."""
        return {
            "id": str(instance.pk),
            "interaction": str(instance.interaction_id),
            "manager": {
                "id": instance.manager_id,
                "email": instance.manager.email,
                "full_name": instance.manager.get_full_name(),
            },
            "assigned_by": None,
            "unassigned_at": None,
        }

    def test_filter_by_interaction_ids(self) -> None:
        """Фильтр interaction__ids возвращает историю указанного взаимодействия."""
        interaction = InteractionFactory()
        target = ResponsibleFactory(interaction=interaction)
        ResponsibleFactory()

        response = self.client.get(
            path=self.list_url,
            data={"interaction__ids": str(interaction.pk)},
        )

        # Проверяем, что найдена только запись выбранного взаимодействия
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_by_manager_ids(self) -> None:
        """Фильтр manager__ids возвращает назначения указанных менеджеров."""
        manager = UserFactory()
        target = ResponsibleFactory(manager=manager)
        ResponsibleFactory()

        response = self.client.get(
            path=self.list_url,
            data={"manager__ids": str(manager.pk)},
        )

        # Проверяем, что найдено только назначение выбранного менеджера
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(target.pk)],
        )

    def test_filter_is_current_returns_only_open_records(self) -> None:
        """Фильтр is_current=true возвращает только незакрытые назначения."""
        interaction = InteractionFactory()
        ResponsibleFactory(
            interaction=interaction,
            unassigned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        current = ResponsibleFactory(interaction=interaction)

        response = self.client.get(path=self.list_url, data={"is_current": "true"})

        # Проверяем, что закрытая запись скрыта
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(current.pk)],
        )
