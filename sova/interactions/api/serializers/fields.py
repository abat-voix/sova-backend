from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.interactions.models import Interaction
from sova.interactions.services import visible_interactions


class VisibleInteractionField(serializers.PrimaryKeyRelatedField):
    """
    Ссылка на взаимодействие, видимое автору запроса: чужое отклоняется так же, как несуществующее (400).

    Без проверки через тело запроса можно было бы менять состав чужого взаимодействия.
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("label", _("Взаимодействие"))
        # Полный queryset — для схемы API; проверка идёт по `get_queryset`
        super().__init__(queryset=Interaction.objects.all(), **kwargs)

    def get_queryset(self):
        """Взаимодействия, видимые автору запроса."""
        return visible_interactions(self.context["request"].user)
