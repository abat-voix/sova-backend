from rest_framework import serializers

from sova.catalog.models import B2CClientAddress, OrganizationAddress


class OrganizationAddressSerializer(serializers.ModelSerializer):
    """Адрес организации — публичный; координаты нужны для карты, указываются вместе."""

    class Meta:
        model = OrganizationAddress
        fields = (
            "country_code",
            "region",
            "city",
            "street",
            "house",
            "office",
            "postal_code",
            "lat",
            "lon",
        )
        extra_kwargs = {
            "lat": {"min_value": -90, "max_value": 90},
            "lon": {"min_value": -180, "max_value": 180},
        }

    def validate(self, attrs: dict) -> dict:
        """Широта и долгота — только вместе: одна без другой точку на карте не даёт."""
        if (attrs.get("lat") is None) != (attrs.get("lon") is None):
            raise serializers.ValidationError({"lat": ["Широта и долгота указываются вместе."]})
        return attrs


class B2CClientOpenAddressSerializer(serializers.ModelSerializer):
    """Открытая часть адреса B2C-клиента: страна, регион и город — видны всем, кому доступен каталог."""

    class Meta:
        model = B2CClientAddress
        fields = ("country_code", "region", "city")


class B2CClientRegistrationAddressSerializer(serializers.ModelSerializer):
    """
    Адрес регистрации B2C-клиента целиком. Улица, дом, квартира и индекс — персональные данные: отдаются и
    принимаются только по праву `catalog.personal_data.*`, каждое обращение пишется в журнал.
    """

    class Meta:
        model = B2CClientAddress
        fields = ("country_code", "region", "city", "street", "house", "apartment", "postal_code")
        read_only_fields = ("country_code", "region", "city")
