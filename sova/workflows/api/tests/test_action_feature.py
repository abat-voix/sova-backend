from rest_framework import status
from rest_framework.test import APITestCase

from sova.core.tests.base import BaseApiTestMixin
from sova.workflows.models import ActionFeature
from sova.workflows.tests.factories import ActionFeatureFactory, WorkflowActionFactory


class ActionFeatureApiTestCase(BaseApiTestMixin, APITestCase):
    """Тесты CRUD /api/workflows/action-features/."""

    url_basename = "workflows:action-feature"
    model = ActionFeature

    def create_instance(self, **kwargs) -> ActionFeature:
        return ActionFeatureFactory(**kwargs)

    def get_expected_data(self, instance: ActionFeature) -> dict:
        return {
            "id": str(instance.pk),
            "code": instance.code,
            "sort_order": instance.sort_order,
            "is_active": instance.is_active,
            "settings": instance.settings,
            "action": {"id": str(instance.action_id), "name": instance.action.name},
        }

    def get_post_data(self) -> dict:
        return {
            "code": "contact_person.create",
            "sort_order": 1,
            "settings": {"source": "manual"},
            "action": str(WorkflowActionFactory().pk),
        }

    def get_change_data(self) -> dict:
        return {"is_active": False, "settings": {"source": "catalog"}}

    def get_search_term(self, instance: ActionFeature) -> str:
        return instance.code

    def test_rejects_non_object_settings(self) -> None:
        response = self.client.post(
            path=self.list_url,
            data={**self.get_post_data(), "settings": ["invalid"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("settings", response.data)

    def test_workflow_definition_contains_features(self) -> None:
        feature = ActionFeatureFactory(settings={"source": "catalog"})

        response = self.client.get(
            f"/api/workflows/workflows/{feature.action.stage.workflow_id}/definition/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(len(response.data["features"]), 1)
        self.assertEqual(
            {
                key: response.data["features"][0][key]
                for key in self.get_expected_data(feature)
            },
            self.get_expected_data(feature),
        )
