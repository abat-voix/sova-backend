from rest_framework import serializers

from sova.catalog.models import University


class UniversityShortSerializer(serializers.ModelSerializer):
    """Вуз — краткое представление для вложенного использования."""

    class Meta:
        model = University
        fields = ("id", "name")


class UniversitySerializer(serializers.ModelSerializer):
    """Вуз — представление для чтения (list/retrieve)."""

    class Meta:
        model = University
        fields = (
            "id",
            "name",
            "inn",
            "external_code",
            "email",
            "phone",
            "is_active",
            "created_at",
            "updated_at",
            "lat",
            "lon",
            "city",
        )


class WriteUniversitySerializer(serializers.ModelSerializer):
    """Вуз — валидация входных данных (create/update)."""

    class Meta:
        model = University
        fields = (
            "id",
            "name",
            "inn",
            "external_code",
            "email",
            "phone",
            "is_active",
        )
