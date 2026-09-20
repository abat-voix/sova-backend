from rest_framework import serializers

from sova.catalog.models import Vendor


class VendorShortSerializer(serializers.ModelSerializer):
    """Вендор — краткое представление для вложенного использования."""

    class Meta:
        model = Vendor
        fields = ("id", "name")


class VendorSerializer(serializers.ModelSerializer):
    """Вендор — представление для чтения (list/retrieve)."""

    class Meta:
        model = Vendor
        fields = (
            "id",
            "name",
            "external_code",
            "is_active",
            "created_at",
            "updated_at",
        )


class WriteVendorSerializer(serializers.ModelSerializer):
    """Вендор — валидация входных данных (create/update)."""

    class Meta:
        model = Vendor
        fields = (
            "id",
            "name",
            "external_code",
            "is_active",
        )
