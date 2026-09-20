from django.db.models import Model
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters


class NumberInFilter(filters.BaseInFilter, filters.NumberFilter):
    """Фильтр по списку чисел, переданных через запятую."""


class UUIDInFilter(filters.BaseInFilter, filters.UUIDFilter):
    """Фильтр по списку UUID, переданных через запятую."""


class SearchFilterMixin(filters.FilterSet):
    """
    Базовый FilterSet проекта.

    Для каждого поля из `Meta.exact_search_fields` добавляет фильтр
    `<поле>__iexact` — точное совпадение без учёта регистра (код, ИНН, номер
    договора). Фильтры создаются на уровне класса, поэтому попадают в
    OpenAPI-схему так же, как явно объявленные.
    """

    @classmethod
    def get_filters(cls) -> dict:
        """Добавляет `<поле>__iexact` для полей из `Meta.exact_search_fields`."""
        declared = super().get_filters()
        meta = getattr(cls, "Meta", None)
        model: type[Model] | None = getattr(meta, "model", None)
        if model is None:
            return declared

        for field_name in getattr(meta, "exact_search_fields", ()):
            verbose_name = model._meta.get_field(field_name).verbose_name
            declared[f"{field_name}__iexact"] = filters.CharFilter(
                field_name=field_name,
                lookup_expr="iexact",
                label=capfirst(verbose_name),
                help_text=_("Точное совпадение без учёта регистра"),
            )
        return declared
