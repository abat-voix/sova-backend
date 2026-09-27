from django.db.models import QuerySet

from sova.interactions.services import visible_interactions


class VisibleInteractionMixin:
    """
    Ограничивает выборку записями процессов по взаимодействиям, видимым пользователю (`visible_interactions`).

    Наследник задаёт `interaction_lookup` — путь от модели к взаимодействию. Чужие записи недоступны ни в списке,
    ни по id (404), в том числе для действий над ними.
    """

    interaction_lookup: str

    def get_queryset(self) -> QuerySet:
        """Записи по видимым пользователю взаимодействиям."""
        return super().get_queryset().filter(
            **{f"{self.interaction_lookup}__in": visible_interactions(self.request.user)},
        )
