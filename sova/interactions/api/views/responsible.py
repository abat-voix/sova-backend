from sova.core.api.views import SovaReadOnlyViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.api.views.mixins import InteractionPartMixin
from sova.interactions.models import Responsible


class ResponsibleViewSet(InteractionPartMixin, SovaReadOnlyViewSet):
    """
    История назначений ответственных — только чтение; видна вместе со взаимодействием или договором реестра.

    Назначение и снятие выполняются действиями взаимодействия
    `assign-responsible` / `unassign-responsible`.
    """

    read_serializer_class = serializers.ResponsibleSerializer
    serializer_class = serializers.ResponsibleSerializer
    queryset = Responsible.objects.select_related("manager", "assigned_by")
    ordering_fields = "__all__"
    search_fields = ("manager__first_name", "manager__last_name", "manager__email")
    filterset_class = filters.ResponsibleFilter
