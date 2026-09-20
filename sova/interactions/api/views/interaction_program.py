from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.models import InteractionProgram


class InteractionProgramViewSet(SovaBaseViewSet):
    """ИТ-программы во взаимодействиях. Доступны CRUD операции."""

    read_serializer_class = serializers.InteractionProgramSerializer
    serializer_class = serializers.WriteInteractionProgramSerializer
    queryset = InteractionProgram.objects.select_related("it_program")
    ordering_fields = "__all__"
    search_fields = ("it_program__name",)
    filterset_class = filters.InteractionProgramFilter
