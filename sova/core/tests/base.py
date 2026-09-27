import json

from django.db.models import Model
from django.urls import reverse
from rest_framework import status
from rest_framework.utils.encoders import JSONEncoder

from accounts.models import SystemRole, UserRole
from sova.core.tests.factories import UserFactory


class BaseApiTestMixin:
    """
    Типовые тесты CRUD-эндпоинта: list, detail, add, change, delete, search.

    Используется вместе с `APITestCase`. Наследник задаёт `url_basename`
    (`<app_name>:<basename роутера>`), `model` и переопределяет:

    - `create_instance` — создаёт объект через фабрику;
    - `get_expected_data` — ожидаемые поля ответа в формате read-сериализатора;
    - `get_post_data` — данные для POST в формате write-сериализатора;
    - `get_change_data` — данные для PATCH;
    - `get_search_term` — строка поиска, находящая только `instance`.

    Флаги `allow_create`/`allow_update`/`allow_delete` отключают соответствующие
    тесты и проверяют, что метод недоступен (405). `user_role` — прикладная роль
    пользователя клиента для разделов, закрытых политикой ролей.
    """

    url_basename: str
    model: type[Model]
    allow_create: bool = True
    allow_update: bool = True
    allow_delete: bool = True
    user_role: str | None = SystemRole.PLATFORM_ADMIN

    def setUp(self) -> None:
        """Аутентифицирует клиента обычным пользователем."""
        self.user = UserFactory()
        if self.user_role is not None:
            UserRole.objects.create(user=self.user, role=self.user_role)
        self.client.force_authenticate(user=self.user)

    def create_instance(self, **kwargs) -> Model:
        """Создаёт объект тестируемой модели."""
        raise NotImplementedError

    def get_expected_data(self, instance: Model) -> dict:
        """Ожидаемые поля read-представления объекта."""
        raise NotImplementedError

    def get_post_data(self) -> dict:
        """Данные для создания объекта (формат write-сериализатора)."""
        raise NotImplementedError

    def get_change_data(self) -> dict:
        """Данные для частичного обновления объекта."""
        raise NotImplementedError

    def get_search_term(self, instance: Model) -> str | None:
        """Строка поиска, находящая только `instance`; None — поиска нет."""
        return None

    @property
    def list_url(self) -> str:
        """URL списка."""
        return reverse(f"{self.url_basename}-list")

    def detail_url(self, instance: Model) -> str:
        """URL объекта."""
        return reverse(f"{self.url_basename}-detail", args=[instance.pk])

    def assert_data_contains(self, data: dict, expected: dict) -> None:
        """
        Проверяет, что все ожидаемые поля присутствуют в данных ответа.

        Данные приводятся к JSON-виду (UUID и даты — строки), как их увидит клиент.
        """
        data = json.loads(json.dumps(data, cls=JSONEncoder))
        for key, value in expected.items():
            # Проверяем значение поля ответа
            self.assertEqual(data[key], value, msg=f"Поле {key}")

    def test_list_returns_instance(self) -> None:
        """Список возвращает объект в формате read-сериализатора."""
        instance = self.create_instance()

        response = self.client.get(path=self.list_url)

        # Проверяем успешный ответ
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Проверяем, что в списке ровно один объект
        self.assertEqual(response.data["count"], 1)
        self.assert_data_contains(
            data=response.data["results"][0],
            expected=self.get_expected_data(instance),
        )

    def test_list_requires_authentication(self) -> None:
        """Анонимный запрос списка отклоняется."""
        self.client.force_authenticate(user=None)

        response = self.client.get(path=self.list_url)

        # Проверяем, что доступ запрещён
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_detail_returns_expected_data(self) -> None:
        """Детальный запрос возвращает объект в формате read-сериализатора."""
        instance = self.create_instance()

        response = self.client.get(path=self.detail_url(instance))

        # Проверяем успешный ответ
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_data_contains(
            data=response.data,
            expected=self.get_expected_data(instance),
        )

    def test_add_creates_instance(self) -> None:
        """POST с валидными данными создаёт объект и возвращает read-представление."""
        if not self.allow_create:
            self.skipTest("Создание не поддерживается")
        data = self.get_post_data()

        response = self.client.post(path=self.list_url, data=data, format="json")

        # Проверяем, что объект создан
        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            msg=response.data,
        )
        instance = self.model.objects.get(pk=response.data["id"])
        # Проверяем, что ответ в формате read-сериализатора
        self.assert_data_contains(
            data=response.data,
            expected=self.get_expected_data(instance),
        )

    def test_change_updates_instance(self) -> None:
        """PATCH обновляет объект и возвращает read-представление."""
        if not self.allow_update:
            self.skipTest("Обновление не поддерживается")
        instance = self.create_instance()

        response = self.client.patch(
            path=self.detail_url(instance),
            data=self.get_change_data(),
            format="json",
        )

        # Проверяем успешный ответ
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        instance.refresh_from_db()
        # Проверяем, что ответ отражает сохранённое состояние
        self.assert_data_contains(
            data=response.data,
            expected=self.get_expected_data(instance),
        )

    def test_delete_removes_instance(self) -> None:
        """DELETE удаляет объект."""
        if not self.allow_delete:
            self.skipTest("Удаление не поддерживается")
        instance = self.create_instance()

        response = self.client.delete(path=self.detail_url(instance))

        # Проверяем, что объект удалён
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(self.model.objects.filter(pk=instance.pk).exists())

    def test_disallowed_methods_return_405(self) -> None:
        """Отключённые методы возвращают 405."""
        instance = self.create_instance()

        if not self.allow_create:
            response = self.client.post(path=self.list_url, data={}, format="json")
            # Проверяем, что POST недоступен
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        if not self.allow_update:
            response = self.client.patch(
                path=self.detail_url(instance),
                data={},
                format="json",
            )
            # Проверяем, что PATCH недоступен
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        if not self.allow_delete:
            response = self.client.delete(path=self.detail_url(instance))
            # Проверяем, что DELETE недоступен
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_search_finds_only_matching_instance(self) -> None:
        """Поиск возвращает только подходящий объект."""
        instance = self.create_instance()
        term = self.get_search_term(instance)
        if term is None:
            self.skipTest("Поиск не поддерживается")
        self.create_instance()

        response = self.client.get(path=self.list_url, data={"search": term})

        # Проверяем, что найден только искомый объект
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(instance.pk)],
        )
