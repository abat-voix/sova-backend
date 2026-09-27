from rest_framework import serializers


class DocumentTemplateFieldSerializer(serializers.Serializer):
    path = serializers.CharField(help_text="Путь в JSON; [] обозначает элемент списка.")
    label = serializers.CharField()
    type = serializers.ChoiceField(choices=("string", "date", "decimal", "integer", "boolean", "object", "array"))
    snippet = serializers.CharField(allow_blank=True, help_text="Готовый фрагмент для вставки в DOCX.")


class DocumentTemplateFieldsSerializer(serializers.Serializer):
    kind = serializers.CharField()
    fields = DocumentTemplateFieldSerializer(many=True)
