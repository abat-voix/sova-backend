from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from sova.core.api.serializers import UserShortSerializer
from sova.interactions.api.serializers import InteractionShortSerializer
from sova.workflows.api.serializers import WorkflowShortSerializer


class BoardRefSerializer(serializers.Serializer):
    """Ссылка на этап или действие определения workflow: id и название."""

    id = serializers.UUIDField(label=_("ID"), help_text=_("Идентификатор в определении workflow"))
    name = serializers.CharField(label=_("Название"), help_text=_("Текущее название в определении workflow"))


class BoardOutcomeSerializer(serializers.Serializer):
    """Исход, который можно выбрать при завершении действия."""

    id = serializers.UUIDField(label=_("ID"), help_text=_("Передаётся при завершении действия"))
    code = serializers.CharField(label=_("Код"), help_text=_("Стабильный код исхода внутри действия"))
    name = serializers.CharField(label=_("Название"), help_text=_("Подпись исхода для пользователя"))
    comment_required = serializers.BooleanField(
        label=_("Нужен комментарий"),
        help_text=_("Без комментария исход не будет принят"),
    )
    attachment_required = serializers.BooleanField(
        label=_("Нужно вложение"),
        help_text=_("Файл нужно загрузить к исполнению действия до завершения"),
    )


class BoardResultSerializer(serializers.Serializer):
    """Результат выполненного действия."""

    outcome_name = serializers.CharField(label=_("Исход"), help_text=_("Название исхода на момент выполнения"))
    comment = serializers.CharField(
        label=_("Комментарий"),
        help_text=_("Комментарий при завершении; может быть пустым"),
    )
    created_at = serializers.DateTimeField(label=_("Зафиксировано"), help_text=_("Момент завершения действия"))
    created_by = UserShortSerializer(
        allow_null=True,
        label=_("Автор"),
        help_text=_("Кто завершил действие; пусто, если пользователь удалён"),
    )


class BoardActionSerializer(serializers.Serializer):
    """Действие на доске: последнее исполнение, результат, вложения и доступные исходы."""

    id = serializers.UUIDField(label=_("ID"), help_text=_("Идентификатор исполнения; по нему завершают действие"))
    action = BoardRefSerializer(label=_("Действие"), help_text=_("Определение действия в workflow"))
    name = serializers.CharField(label=_("Название"), help_text=_("Название действия на момент запуска процесса"))
    status = serializers.CharField(label=_("Статус"), help_text=_("pending, in_progress или completed"))
    is_optional = serializers.BooleanField(
        label=_("Необязательное"),
        help_text=_("Необязательное действие не мешает закрыть этап и остаётся доступным после его закрытия"),
    )
    starts_by_transition_only = serializers.BooleanField(
        label=_("Только по переходу"),
        help_text=_("Действие запускается переходом по исходу другого действия, а не вместе с этапом"),
    )
    is_triggered = serializers.BooleanField(
        label=_("Запущено переходом"),
        help_text=_("Для действия «только по переходу»: запущено ли оно; иначе оно ждёт запуска"),
    )
    execution_no = serializers.IntegerField(
        label=_("Номер исполнения"),
        help_text=_("Больше единицы, если действие выполняется повторно после возврата или перехода"),
    )
    planned_start = serializers.DateTimeField(
        allow_null=True,
        label=_("Плановое начало"),
        help_text=_("Момент запуска"),
    )
    planned_end = serializers.DateTimeField(
        allow_null=True,
        label=_("Плановое окончание"),
        help_text=_("Плановое начало плюс плановая длительность действия; пусто без длительности"),
    )
    actual_start = serializers.DateTimeField(
        allow_null=True,
        label=_("Фактическое начало"),
        help_text=_("Момент, когда действие стало доступно"),
    )
    actual_end = serializers.DateTimeField(
        allow_null=True,
        label=_("Фактическое окончание"),
        help_text=_("Момент завершения; пусто, пока действие не выполнено"),
    )
    is_overdue = serializers.BooleanField(
        label=_("Просрочено"),
        help_text=_("Действие в работе, плановое окончание которого прошло"),
    )
    responsible = UserShortSerializer(
        allow_null=True,
        label=_("Ответственный"),
        help_text=_("Действующий менеджер взаимодействия или тот, кто завершил действие"),
    )
    result = BoardResultSerializer(
        allow_null=True,
        label=_("Результат"),
        help_text=_("Пусто, пока последнее исполнение не выполнено"),
    )
    attachments_count = serializers.IntegerField(
        label=_("Вложений"),
        help_text=_("Число файлов, приложенных к исполнению"),
    )
    available_outcomes = BoardOutcomeSerializer(
        many=True,
        label=_("Доступные исходы"),
        help_text=_("Активные исходы действия; пусто, если действие не в работе"),
    )


class BoardReturnOptionSerializer(serializers.Serializer):
    """Этап, на который можно вернуться при отмене этапа."""

    id = serializers.UUIDField(label=_("ID"), help_text=_("Передаётся как return_to при отмене этапа"))
    stage_name = serializers.CharField(label=_("Название"), help_text=_("Название этапа для выбора пользователем"))


class BoardStageSerializer(serializers.Serializer):
    """Этап на доске: статус, время, варианты возврата и действия."""

    id = serializers.UUIDField(label=_("ID"), help_text=_("Идентификатор экземпляра этапа; по нему отменяют этап"))
    stage = BoardRefSerializer(label=_("Этап"), help_text=_("Определение этапа в workflow"))
    status = serializers.CharField(label=_("Статус"), help_text=_("pending, in_progress или completed"))
    started_at = serializers.DateTimeField(allow_null=True, label=_("Открыт"), help_text=_("Пусто, пока этап ожидает"))
    completed_at = serializers.DateTimeField(
        allow_null=True,
        label=_("Закрыт"),
        help_text=_("Пусто, пока этап не закрыт"),
    )
    return_options = BoardReturnOptionSerializer(
        many=True,
        label=_("Варианты возврата"),
        help_text=_("Предшественники, если этап в работе; пусто, если отменять его нельзя"),
    )
    actions = BoardActionSerializer(
        many=True,
        label=_("Действия"),
        help_text=_("Последнее исполнение каждого действия этапа"),
    )


class BoardContextGroupSerializer(serializers.Serializer):
    """Группа этапов одного направления, программы или продукта."""

    context_type = serializers.CharField(
        label=_("Тип контекста"),
        help_text=_("direction, program или product"),
    )
    context_id = serializers.UUIDField(
        label=_("ID контекста"),
        help_text=_("Идентификатор направления, программы или продукта взаимодействия"),
    )
    title = serializers.CharField(label=_("Название"), help_text=_("Название направления, программы или продукта"))
    parent_id = serializers.UUIDField(
        allow_null=True,
        label=_("Родитель"),
        help_text=_("Для продукта — программа взаимодействия, если он к ней привязан; иначе пусто"),
    )
    stages = BoardStageSerializer(many=True, label=_("Этапы"), help_text=_("Этапы этого контекста по порядку показа"))


class WorkflowBoardSerializer(serializers.Serializer):
    """Доска процесса — весь путь взаимодействия для визуализации одним ответом."""

    id = serializers.UUIDField(label=_("ID"), help_text=_("Идентификатор процесса"))
    status = serializers.CharField(label=_("Статус"), help_text=_("running или completed"))
    started_at = serializers.DateTimeField(label=_("Начат"), help_text=_("Момент запуска процесса"))
    completed_at = serializers.DateTimeField(
        allow_null=True,
        label=_("Завершён"),
        help_text=_("Пусто, пока процесс идёт"),
    )
    workflow = WorkflowShortSerializer(label=_("Workflow"), help_text=_("Шаблон, по которому идёт процесс"))
    interaction = InteractionShortSerializer(
        label=_("Взаимодействие"),
        help_text=_("Вуз или клиент, с которым ведётся работа"),
    )
    interaction_stages = BoardStageSerializer(
        many=True,
        label=_("Этапы взаимодействия"),
        help_text=_("Этапы всего взаимодействия по порядку показа"),
    )
    context_groups = BoardContextGroupSerializer(
        many=True,
        label=_("Группы контекстов"),
        help_text=_("Этапы направлений, программ и продуктов, сгруппированные по контексту"),
    )
