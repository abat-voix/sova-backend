from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.policy import Action
from sova.catalog.api import filters, serializers
from sova.catalog.api.views.mixins import CatalogPolicyMixin
from sova.catalog.models import ContactPerson
from sova.catalog.services import contact_affiliation_service, contact_matching_service
from sova.core.api.views import SovaBaseViewSet


class ContactPersonViewSet(CatalogPolicyMixin, SovaBaseViewSet):
    """
    Контактные лица — люди со связями с организациями, B2C-клиентами и вендорами. Доступны CRUD операции.

    Связи создаются и меняются через `/organization-contacts/`, `/b2c-client-contacts/`, `/vendor-contacts/`;
    там же создаётся новый человек вместе со связью (`new_contact`).
    """

    read_serializer_class = serializers.ContactPersonSerializer
    serializer_class = serializers.WriteContactPersonSerializer
    queryset = contact_affiliation_service.prefetch_links(ContactPerson.objects.all())
    ordering_fields = "__all__"
    search_fields = (
        "full_name",
        "email",
        "phone",
        "telegram",
        "organization_links__position",
        "b2c_client_links__position",
        "vendor_links__position",
    )
    filterset_class = filters.ContactPersonFilter
    policy_actions = {**CatalogPolicyMixin.policy_actions, "possible_duplicates": Action.CATALOG_READ}

    def perform_destroy(self, instance: ContactPerson) -> None:
        """Человек удаляется вместе со связями, если ни одна не используется во взаимодействии."""
        contact_affiliation_service.delete_contact(contact=instance)

    @extend_schema(
        parameters=[serializers.PossibleDuplicatesQuerySerializer],
        responses={200: serializers.ContactPersonSerializer(many=True)},
    )
    @action(
        methods=["GET"],
        detail=False,
        url_path="possible-duplicates",
        pagination_class=None,
        filter_backends=[],
    )
    def possible_duplicates(self, request: Request) -> Response:
        """Люди, похожие на указанного по ФИО, email, телефону или Telegram — подсказка «возможно, это он»."""
        query = serializers.PossibleDuplicatesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data
        contacts = contact_matching_service.possible_duplicates(
            full_name=params["full_name"],
            email=params["email"],
            phone=params["phone"],
            telegram=params["telegram"],
            exclude_id=params["exclude"],
        )
        prefetched = {
            contact.pk: contact
            for contact in self.get_queryset().filter(pk__in=[contact.pk for contact in contacts])
        }
        return Response(
            serializers.ContactPersonSerializer(
                [prefetched[contact.pk] for contact in contacts],
                many=True,
                context=self.get_serializer_context(),
            ).data
        )
