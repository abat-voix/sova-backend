from rest_framework import mixins, status
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.viewsets import GenericViewSet


class ReadWriteSerializerMixin:
    """
    Разделение сериализаторов на read и write.

    `read_serializer_class` используется для `list`/`retrieve` и для тела ответа
    на запись; обычный `serializer_class` — для валидации и сохранения
    (`create`/`update`) и для `@action` со своим `serializer_class`.
    """

    read_serializer_class: type[BaseSerializer] | None = None

    def get_serializer_class(self) -> type[BaseSerializer]:
        """Возвращает read-сериализатор для list/retrieve, иначе — write."""
        if self.read_serializer_class is not None and self.action in (
            "list",
            "retrieve",
        ):
            return self.read_serializer_class
        return super().get_serializer_class()

    def get_response_serializer(
        self,
        instance,
        **kwargs,
    ) -> BaseSerializer:
        """Сериализатор тела ответа на запись — read-представление объекта."""
        serializer_class = self.read_serializer_class or self.serializer_class
        kwargs.setdefault("context", self.get_serializer_context())
        return serializer_class(instance, **kwargs)


class ReadWriteCreateModelMixin(ReadWriteSerializerMixin, mixins.CreateModelMixin):
    """Создание: валидация write-сериализатором, ответ — read-сериализатором."""

    def create(self, request, *args, **kwargs) -> Response:
        """Создаёт объект и возвращает его read-представление."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        response_serializer = self.get_response_serializer(serializer.instance)
        return Response(
            data=response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(response_serializer.data),
        )


class ReadWriteUpdateModelMixin(ReadWriteSerializerMixin, mixins.UpdateModelMixin):
    """Обновление: валидация write-сериализатором, ответ — read-сериализатором."""

    def update(self, request, *args, **kwargs) -> Response:
        """Обновляет объект (PUT/PATCH) и возвращает его read-представление."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # Сбрасываем prefetch-кэш, чтобы read-ответ отражал изменения M2M
        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        response_serializer = self.get_response_serializer(serializer.instance)
        return Response(
            data=response_serializer.data,
            status=status.HTTP_200_OK,
        )


class SovaReadOnlyViewSet(
    ReadWriteSerializerMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    """Базовый ViewSet только для чтения (list, retrieve)."""


class SovaBaseViewSet(
    ReadWriteCreateModelMixin,
    ReadWriteUpdateModelMixin,
    mixins.DestroyModelMixin,
    SovaReadOnlyViewSet,
):
    """
    Базовый ViewSet проекта — полный CRUD с раздельными read/write сериализаторами.

    Наследник задаёт `read_serializer_class`, `serializer_class` (write),
    `queryset`, `ordering_fields`, `search_fields` и `filterset_class`.
    """
