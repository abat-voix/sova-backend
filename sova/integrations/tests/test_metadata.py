from django.test import SimpleTestCase

from sova.integrations.metadata import all_entities, entity_metadata


class IntegrationMetadataTest(SimpleTestCase):
    def test_catalog_comes_from_explicit_serializers(self):
        entities = {item["code"]: item for item in all_entities()}
        self.assertIn("workflow", entities)
        fields = {field["name"]: field for field in entities["workflow"]["fields"]}
        self.assertEqual(fields["id"]["type"], "uuid")
        self.assertTrue(fields["id"]["read_only"])
        self.assertIn("is_active", fields)

    def test_metadata_contains_mapping_relevant_properties(self):
        item = entity_metadata(
            "example",
            {"label": "Example", "serializer": "sova.integrations.api.serializers.IntegrationPayloadSerializer"},
        )
        field = next(field for field in item["fields"] if field["name"] == "payload")
        self.assertEqual(field["type"], "json")
