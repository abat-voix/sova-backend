from rest_framework import status
from rest_framework.response import Response


class ReadWriteSerializerMixin:
    """
    Разделяет сериализатор ViewSet'а на read (list/retrieve) и write (create/update).

    `read_serializer_class` — представление данных в ответе, `serializer_class`
    (обычный атрибут DRF) — валидация входных данных. Тело ответа на create/update
    всегда строится через read-сериализатор поверх сохранённого инстанса, а не
    через write-сериализатор, которым данные были провалидированы.
    """

    read_serializer_class = None

    def get_serializer_class(self):
        """Read-сериализатор для list/retrieve, иначе обычный serializer_class."""
        if getattr(self, "action", None) in ("list", "retrieve") and self.read_serializer_class is not None:
            return self.read_serializer_class
        return super().get_serializer_class()

    def get_response_serializer(self, instance):
        """Сериализатор для построения тела ответа на create/update."""
        serializer_class = self.read_serializer_class or self.get_serializer_class()
        return serializer_class(instance, context=self.get_serializer_context())

    def create(self, request, *args, **kwargs):
        """Валидация через write-сериализатор, ответ — через read-сериализатор."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        response_serializer = self.get_response_serializer(serializer.instance)
        return Response(
            data=response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def update(self, request, *args, **kwargs):
        """Валидация через write-сериализатор, ответ — через read-сериализатор."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        response_serializer = self.get_response_serializer(serializer.instance)
        return Response(data=response_serializer.data, status=status.HTTP_200_OK)
