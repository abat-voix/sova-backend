from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.training.models import TrainingApplication, TrainingStream
from sova.training.services.visibility import visible_applications, visible_streams


class VisibleStreamField(serializers.PrimaryKeyRelatedField):
    """Поток, видимый автору запроса: чужой отклоняется так же, как несуществующий (400)."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("label", _("Поток"))
        # Полный queryset — для схемы API; проверка идёт по `get_queryset`
        super().__init__(queryset=TrainingStream.objects.all(), **kwargs)

    def get_queryset(self):
        """Потоки, видимые автору запроса."""
        return visible_streams(self.context["request"].user)


class VisibleApplicationField(serializers.PrimaryKeyRelatedField):
    """Заявка потока, видимого автору запроса: чужая отклоняется так же, как несуществующая (400)."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("label", _("Заявка"))
        super().__init__(queryset=TrainingApplication.objects.all(), **kwargs)

    def get_queryset(self):
        """Заявки видимых потоков."""
        return visible_applications(self.context["request"].user)
