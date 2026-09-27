from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.catalog.api.serializers.catalog_import import CatalogImportRowWarningSerializer
from sova.training.api.serializers.fields import VisibleStreamField


class LearnerImportSerializer(serializers.Serializer):
    """Загрузка файла «Пользователи»: с потоком — сразу заявка на него, без потока — только обучающиеся."""

    file = serializers.FileField(
        validators=[FileExtensionValidator(allowed_extensions=("xlsx", "xls"))],
        label=_("Файл"),
        help_text=_("Первый лист xlsx или xls; колонки — по маппингу типа learner (/api/catalog/import-mappings/)"),
    )
    stream = VisibleStreamField(
        required=False,
        allow_null=True,
        help_text=_("Поток: создаётся заявка на него, обучающиеся из файла становятся её участниками"),
    )


class LearnerImportResultSerializer(serializers.Serializer):
    """Результат загрузки файла «Пользователи»."""

    created = serializers.IntegerField(label=_("Создано"), help_text=_("Новые обучающиеся"))
    updated = serializers.IntegerField(
        label=_("Обновлено"),
        help_text=_("Обучающиеся, найденные по email или телефону и дополненные данными файла"),
    )
    application = serializers.UUIDField(
        allow_null=True,
        label=_("Заявка"),
        help_text=_("Заявка, созданная на выбранный поток; пусто — поток не выбран или добавлять было некого"),
    )
    warnings = CatalogImportRowWarningSerializer(
        many=True,
        label=_("Предупреждения"),
        help_text=_("Например, обучающийся уже есть в заявке этого потока и пропущен"),
    )
