from accounts.policy import Action
from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.models import License
from sova.interactions.services import license_service, visible_licenses


class LicenseViewSet(SovaBaseViewSet):
    """
    Лицензии на продукты взаимодействий. Доступны CRUD операции.

    Создание лицензии для пары (договор, продукт), у которой уже есть действующая,
    перезаключает её: прежняя закрывается и остаётся в истории.
    """

    read_serializer_class = serializers.LicenseSerializer
    serializer_class = serializers.WriteLicenseSerializer
    queryset = License.objects.select_related(
        "contract",
        "interaction_product__product",
        "created_by",
    )
    ordering_fields = "__all__"
    search_fields = (
        "contract__contract_number",
        "interaction_product__product__name",
    )
    filterset_class = filters.LicenseFilter
    policy_actions = {
        "list": Action.LICENSES_READ,
        "retrieve": Action.LICENSES_READ,
        "create": Action.LICENSES_CREATE,
        "update": Action.LICENSES_UPDATE,
        "partial_update": Action.LICENSES_UPDATE,
        "destroy": Action.LICENSES_DELETE,
    }

    def get_queryset(self):
        """Лицензии только видимых пользователю договоров."""
        return super().get_queryset().filter(pk__in=visible_licenses(self.request.user))

    def perform_create(self, serializer: serializers.WriteLicenseSerializer) -> None:
        """Выдача лицензии через сервис — с закрытием прежней действующей."""
        data = serializer.validated_data
        serializer.instance = license_service.create_license(
            contract=data["contract"],
            interaction_product=data["interaction_product"],
            signed_at=data.get("signed_at"),
            valid_until_year=data.get("valid_until_year"),
            is_signed=data.get("is_signed", False),
            created_by=self.request.user,
        )
