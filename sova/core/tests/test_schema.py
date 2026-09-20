from django.test import TestCase
from drf_spectacular.generators import SchemaGenerator


class OpenApiSchemaTest(TestCase):
    """Тесты OpenAPI-схемы, по которой строится Swagger UI."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Генерирует схему один раз для всего класса."""
        cls.paths = SchemaGenerator().get_schema(request=None, public=True)["paths"]

    def response_ref(self, path: str, method: str, code: str) -> str:
        """Возвращает имя схемы, которой описан ответ метода."""
        content = self.paths[path][method]["responses"][code]["content"]
        return content["application/json"]["schema"]["$ref"].rsplit("/", 1)[-1]

    def request_ref(self, path: str, method: str) -> str:
        """Возвращает имя схемы, которой описано тело запроса метода."""
        content = self.paths[path][method]["requestBody"]["content"]
        schema = next(iter(content.values()))["schema"]
        return schema["$ref"].rsplit("/", 1)[-1]

    def test_write_methods_describe_request_with_write_and_response_with_read(self) -> None:
        """POST/PUT/PATCH принимают write-сериализатор, а отвечают read-сериализатором."""
        list_path = "/api/catalog/it-programs/"
        detail_path = "/api/catalog/it-programs/{id}/"

        # Проверяем тело запроса — write-сериализатор
        self.assertEqual(self.request_ref(list_path, "post"), "WriteITProgram")
        self.assertEqual(self.request_ref(detail_path, "patch"), "PatchedWriteITProgram")
        # Проверяем ответ — read-сериализатор, как и фактически возвращает API
        self.assertEqual(self.response_ref(list_path, "post", "201"), "ITProgram")
        self.assertEqual(self.response_ref(detail_path, "put", "200"), "ITProgram")
        self.assertEqual(self.response_ref(detail_path, "patch", "200"), "ITProgram")
        self.assertEqual(self.response_ref(detail_path, "get", "200"), "ITProgram")

    def test_custom_action_keeps_its_own_response(self) -> None:
        """Ответ @action со своим сериализатором не подменяется read-сериализатором."""
        path = "/api/interactions/interactions/{id}/assign-responsible/"

        # Проверяем, что ответ описан назначением ответственного, а не взаимодействием
        self.assertEqual(self.response_ref(path, "post", "201"), "Responsible")
