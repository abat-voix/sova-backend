from drf_spectacular.openapi import AutoSchema


class SovaAutoSchema(AutoSchema):
    """
    Схема OpenAPI с учётом разделения read/write сериализаторов.

    Для `create`/`update`/`partial_update` ViewSet принимает write-сериализатор,
    но ответ формирует read-сериализатором (`ReadWriteSerializerMixin`).
    Без этой подмены Swagger описывал бы ответ теми же полями, что и запрос.
    Кастомные `@action` со своим `serializer_class` не затрагиваются.
    """

    def get_response_serializers(self):
        """Возвращает read-сериализатор как схему ответа на запись."""
        read_serializer_class = getattr(self.view, "read_serializer_class", None)
        if read_serializer_class is not None and getattr(self.view, "action", None) in (
            "create",
            "update",
            "partial_update",
        ):
            return read_serializer_class
        return super().get_response_serializers()
