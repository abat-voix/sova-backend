from sova.core.api.views import SovaBaseViewSet
from sova.interactions.api import filters, serializers
from sova.interactions.api.views.mixins import InteractionPartMixin, SyncProcessesMixin
from sova.interactions.models import InteractionProgram


class InteractionProgramViewSet(InteractionPartMixin, SyncProcessesMixin, SovaBaseViewSet):
    """
    Программы во взаимодействиях. Доступны CRUD операции.

    Видны и изменяются вместе со взаимодействием (`InteractionPartMixin`). Изменение состава сразу досоздаёт этапы
    в идущих процессах взаимодействия.
    """

    read_serializer_class = serializers.InteractionProgramSerializer
    serializer_class = serializers.WriteInteractionProgramSerializer
    queryset = InteractionProgram.objects.select_related("program", "program__direction")
    ordering_fields = "__all__"
    search_fields = ("program__name",)
    filterset_class = filters.InteractionProgramFilter
