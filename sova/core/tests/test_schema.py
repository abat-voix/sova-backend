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
        list_path = "/api/catalog/programs/"
        detail_path = "/api/catalog/programs/{id}/"

        # Проверяем тело запроса — write-сериализатор
        self.assertEqual(self.request_ref(list_path, "post"), "WriteProgram")
        self.assertEqual(self.request_ref(detail_path, "patch"), "PatchedWriteProgram")
        # Проверяем ответ — read-сериализатор, как и фактически возвращает API
        self.assertEqual(self.response_ref(list_path, "post", "201"), "Program")
        self.assertEqual(self.response_ref(detail_path, "put", "200"), "Program")
        self.assertEqual(self.response_ref(detail_path, "patch", "200"), "Program")
        self.assertEqual(self.response_ref(detail_path, "get", "200"), "Program")

    def test_custom_action_keeps_its_own_response(self) -> None:
        """Ответ @action со своим сериализатором не подменяется read-сериализатором."""
        path = "/api/interactions/interactions/{id}/assign-responsible/"

        # Проверяем, что ответ описан назначением ответственного, а не взаимодействием
        self.assertEqual(self.response_ref(path, "post", "201"), "Responsible")

    def test_engine_endpoints_are_documented_with_their_own_schemas(self) -> None:
        """Эндпоинты движка описаны своими сериализаторами запроса и ответа."""
        base = "/api/processes"
        # Проверяем запуск процесса: write на входе, read на выходе
        self.assertEqual(self.request_ref(f"{base}/workflow-instances/", "post"), "WriteWorkflowInstance")
        self.assertEqual(self.response_ref(f"{base}/workflow-instances/", "post", "201"), "WorkflowInstance")
        # Проверяем завершение действия
        complete = f"{base}/action-instances/{{id}}/complete/"
        self.assertEqual(self.request_ref(complete, "post"), "CompleteAction")
        self.assertEqual(self.response_ref(complete, "post", "200"), "CompleteActionResult")
        # Проверяем отмену этапа
        cancel = f"{base}/stage-instances/{{id}}/cancel/"
        self.assertEqual(self.request_ref(cancel, "post"), "CancelStage")
        self.assertEqual(self.response_ref(cancel, "post", "200"), "CancelStageResult")
        # Проверяем доску процесса
        self.assertEqual(self.response_ref(f"{base}/workflow-instances/{{id}}/board/", "get", "200"), "WorkflowBoard")

    def test_stages_actions_and_results_are_read_only(self) -> None:
        """Этапы, действия и результаты процесса доступны только для чтения."""
        for path in ("stage-instances", "action-instances", "action-results"):
            with self.subTest(path=path):
                # Проверяем, что создания нет
                self.assertNotIn("post", self.paths[f"/api/processes/{path}/"])
