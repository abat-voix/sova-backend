"""
Готовые декларации шаблонов workflow.

Пресет — заготовка для администратора: `manage.py create_workflow_template` собирает по нему
шаблон, дальше его правят через API или Django Admin. Правила комментариев и вложений намеренно
заданы по минимуму — их включают на исходах под свой процесс.
"""

from sova.processes.enum import StageInstanceContextType
from sova.workflows.enum import Audience
from sova.workflows.schemas import ActionSpec, FeatureSpec, OutcomeSpec, StageSpec, WorkflowSpec

BASE_B2B_PRESET = WorkflowSpec(
    code="base-b2b",
    name="Базовый процесс работы с вузом",
    audience=Audience.B2B,
    description=(
        "Путь взаимодействия с вузом: от поиска контакта до сопровождения. "
        "Поставка ПО идёт по каждому продукту взаимодействия, обучение — по каждой программе."
    ),
    stale_threshold_days=365,
    stages=(
        StageSpec(
            name="Подготовка и контакт",
            type=StageInstanceContextType.INTERACTION,
            description="Выход на вуз и первая встреча.",
            actions=(
                ActionSpec(
                    name="Найти контакт",
                    description="Найти контактное лицо вуза и зафиксировать его в справочнике.",
                    duration_days=5,
                    features=(FeatureSpec("contact_person.create"), FeatureSpec("contact_person.select")),
                ),
                ActionSpec(
                    name="Связаться с вузом",
                    description="Первый контакт: письмо или звонок.",
                    duration_days=5,
                    after=("Найти контакт",),
                ),
                ActionSpec(
                    name="Провести встречу",
                    description="Встреча с вузом: интересы, ограничения, следующий шаг.",
                    duration_days=10,
                    after=("Связаться с вузом",),
                ),
            ),
        ),
        StageSpec(
            name="Согласование и документы",
            type=StageInstanceContextType.INTERACTION,
            description="Документы и договор.",
            after=("Подготовка и контакт",),
            actions=(
                ActionSpec(
                    name="Подготовить документы",
                    description="Комплект документов под договор с вузом.",
                    duration_days=10,
                    features=(FeatureSpec("contract.create"), FeatureSpec("contract.file.upload")),
                ),
                ActionSpec(
                    name="Согласовать документы",
                    description="Согласование комплекта с вузом.",
                    duration_days=15,
                    after=("Подготовить документы",),
                    features=(FeatureSpec("contract.update"), FeatureSpec("contract.file.upload")),
                    outcomes=(
                        OutcomeSpec(code="done", name="Согласовано"),
                        OutcomeSpec(
                            code="revision",
                            name="Нужны правки",
                            is_comment_required=True,
                            starts="Доработать документы",
                        ),
                    ),
                ),
                ActionSpec(
                    name="Доработать документы",
                    description="Правки по замечаниям вуза. Запускается исходом «Нужны правки».",
                    duration_days=5,
                    is_trigger_only=True,
                    features=(FeatureSpec("contract.update"), FeatureSpec("contract.file.upload")),
                ),
                ActionSpec(
                    name="Подписать договор",
                    description="Подписание договора и его регистрация в СОВА.",
                    duration_days=15,
                    after=("Согласовать документы",),
                    outcomes=(OutcomeSpec(code="done", name="Договор подписан"),),
                    features=(FeatureSpec("contract.sign"), FeatureSpec("contract.file.upload")),
                ),
            ),
        ),
        StageSpec(
            name="Поставка ПО",
            type=StageInstanceContextType.PRODUCT,
            description="Этап на каждый продукт взаимодействия.",
            after=("Согласование и документы",),
            actions=(
                ActionSpec(
                    name="Передать лицензию",
                    description="Передать вузу лицензию на продукт.",
                    duration_days=10,
                    features=(FeatureSpec("license.create"), FeatureSpec("license.update")),
                ),
                ActionSpec(
                    name="Установить ПО",
                    description="Установка продукта на стороне вуза.",
                    duration_days=15,
                    after=("Передать лицензию",),
                ),
            ),
        ),
        StageSpec(
            name="Обучение преподавателей",
            type=StageInstanceContextType.PROGRAM,
            description="Этап на каждую программу взаимодействия.",
            after=("Поставка ПО",),
            actions=(
                ActionSpec(
                    name="Обучить преподавателей",
                    description="Обучение преподавателей вуза по программе.",
                    duration_days=30,
                ),
                ActionSpec(
                    name="Обновить образовательную программу",
                    description="Включение материалов в образовательную программу вуза.",
                    duration_days=30,
                    after=("Обучить преподавателей",),
                ),
            ),
        ),
        StageSpec(
            name="Сопровождение",
            type=StageInstanceContextType.INTERACTION,
            description="Проверка результата и дальнейшая поддержка вуза.",
            after=("Обучение преподавателей",),
            actions=(
                ActionSpec(
                    name="Проверить результат",
                    description="Сверить результат с договорённостями и зафиксировать итог.",
                    duration_days=30,
                    outcomes=(
                        OutcomeSpec(code="done", name="Результат достигнут"),
                        OutcomeSpec(code="issues", name="Есть замечания", is_comment_required=True),
                    ),
                ),
            ),
        ),
    ),
)
