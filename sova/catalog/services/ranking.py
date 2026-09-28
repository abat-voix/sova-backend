from django.db.models import Case, Count, IntegerField, Model, QuerySet, Value, When

from sova.catalog.models import B2CClient, Direction, Product, Program, University
from sova.interactions.models import InteractionProduct
from sova.training.services.enrollment import training_enrollment_service

# Путь от участника заявки к объекту каталога. Поток создаётся только по программе взаимодействия
# (см. `TrainingStreamService.check_can_create`), поэтому контрагент всегда берётся из взаимодействия.
ENROLLED_PATHS: dict[type[Model], str] = {
    University: "application__stream__interaction_program__interaction__university",
    B2CClient: "application__stream__interaction_program__interaction__b2c_client",
    Program: "application__stream__interaction_program__program",
    Direction: "application__stream__interaction_program__program__direction",
}


class CatalogRankingService:
    """
    Место объекта каталога в рейтинге (`rank`).

    Вузы, B2C-клиенты, программы и направления ранжируются по числу зачисленных людей (оплативших обучение, см.
    `training_enrollment_service`); человек на нескольких потоках считается один раз. Продукты — по числу
    взаимодействий, где продукт активен. Места спортивные: при равенстве делят место, следующее пропускается
    (1, 2, 2, 4). Рейтинг общий — не зависит от того, кто смотрит, и от фильтров списка. Без зачисленных
    (взаимодействий) места нет — `rank` равен `None`.
    """

    def annotate_rank(self, queryset: QuerySet) -> QuerySet:
        """Добавляет к queryset каталога аннотацию `rank`."""
        return queryset.annotate(rank=self.rank_expression(self.ranks(queryset.model)))

    def ranks(self, model: type[Model]) -> dict:
        """Места объектов модели: `{pk: место}`, только для объектов с ненулевым показателем."""
        return self.competition_ranks(self.totals(model))

    @staticmethod
    def totals(model: type[Model]) -> dict:
        """Показатель рейтинга по объектам модели: `{pk: значение}`."""
        if model is Product:
            rows = (
                InteractionProduct.objects
                .filter(is_active=True, interaction__isnull=False)
                .values_list("product")
                .annotate(total=Count("interaction", distinct=True))
                .order_by()
            )
        else:
            path = ENROLLED_PATHS[model]
            rows = (
                training_enrollment_service.enrolled_participants()
                .filter(**{f"{path}__isnull": False})
                .values_list(path)
                .annotate(total=Count("learner", distinct=True))
                .order_by()
            )
        return dict(rows)

    @staticmethod
    def competition_ranks(totals: dict) -> dict:
        """Спортивные места: место — 1 плюс число объектов со строго большим показателем."""
        ranks = {}
        ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
        for position, (pk, total) in enumerate(ordered, start=1):
            previous = ordered[position - 2] if position > 1 else None
            ranks[pk] = ranks[previous[0]] if previous and previous[1] == total else position
        return ranks

    @staticmethod
    def rank_expression(ranks: dict) -> Case | Value:
        """Выражение аннотации `rank` по готовым местам."""
        if not ranks:
            return Value(None, output_field=IntegerField())
        return Case(
            *(When(pk=pk, then=Value(rank)) for pk, rank in ranks.items()),
            default=None,
            output_field=IntegerField(),
        )


catalog_ranking_service = CatalogRankingService()
