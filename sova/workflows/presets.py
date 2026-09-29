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
                    features=tuple(FeatureSpec(code) for code in (
                        "responsible.assign", "responsible.unassign", "contact_person.create",
                        "contact_person.select", "contact_person.link", "contact_person.update",
                    )),
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
                    features=tuple(FeatureSpec(code) for code in (
                        "interaction_direction.add", "interaction_direction.remove",
                        "interaction_program.add", "interaction_program.remove",
                        "interaction_product.add", "interaction_product.remove",
                    )),
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
                    features=(FeatureSpec("contract.create"), FeatureSpec("contract.file.upload"),
                              FeatureSpec("contract.mark_sent")),
                ),
                ActionSpec(
                    name="Согласовать документы",
                    description="Согласование комплекта с вузом.",
                    duration_days=15,
                    after=("Подготовить документы",),
                    features=(FeatureSpec("contract.update"), FeatureSpec("contract.file.upload")),
                    outcomes=(
                        OutcomeSpec(code="done", name="Согласовано", starts="Подписать договор"),
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
                    outcomes=(OutcomeSpec(code="done", name="Правки согласованы", starts="Подписать договор"),),
                    features=(FeatureSpec("contract.update"), FeatureSpec("contract.file.upload"),
                              FeatureSpec("contract.mark_corrected"), FeatureSpec("contract.mark_sent")),
                ),
                ActionSpec(
                    name="Подписать договор",
                    description="Подписание договора и его регистрация в СОВА.",
                    duration_days=15,
                    is_trigger_only=True,
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
                    outcomes=(OutcomeSpec(code="done", name="Лицензия передана", is_comment_required=True),),
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
                    features=(FeatureSpec("training.create"),),
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

BASE_B2C_PRESET = WorkflowSpec(
    code="base-b2c",
    name="Обучение физического лица",
    audience=Audience.B2C,
    description=(
        "Подбор курса, оформление договора, проверка оплаты и зачисление, обучение и итоговая оценка. "
        "Оплата и участники ведутся в заявке потока обучения."
    ),
    stale_threshold_days=180,
    stages=(
        StageSpec(name="Консультация и подбор курса", actions=(
            ActionSpec(name="Уточнить запрос клиента", duration_days=2,
                       description="Проверить контакты физлица в его карточке, согласовать цели и формат обучения.",
                       features=(FeatureSpec("responsible.assign"), FeatureSpec("responsible.unassign"))),
            ActionSpec(name="Подобрать программу обучения", duration_days=2, after=("Уточнить запрос клиента",),
                       features=tuple(FeatureSpec(code) for code in (
                           "interaction_direction.add", "interaction_direction.remove",
                           "interaction_program.add", "interaction_program.remove",
                       ))),
        )),
        StageSpec(name="Договор на обучение", after=("Консультация и подбор курса",), actions=(
            ActionSpec(name="Оформить договор с физлицом", duration_days=2,
                       features=(FeatureSpec("contract.create"), FeatureSpec("contract.file.upload"),
                                 FeatureSpec("contract.mark_sent"))),
            ActionSpec(name="Проверить реквизиты и условия", duration_days=3,
                       after=("Оформить договор с физлицом",),
                       features=(FeatureSpec("contract.update"), FeatureSpec("contract.mark_corrected"),
                                 FeatureSpec("contract.file.upload"), FeatureSpec("contract.mark_sent")),
                       description="Исправить замечания и повторно отправить договор до завершения действия."),
            ActionSpec(name="Подписать договор с клиентом", duration_days=3,
                       after=("Проверить реквизиты и условия",),
                       features=(FeatureSpec("contract.sign"), FeatureSpec("contract.file.upload"))),
        )),
        StageSpec(name="Зачисление и оплата", type=StageInstanceContextType.PROGRAM,
                  after=("Договор на обучение",), actions=(
            ActionSpec(name="Организовать поток обучения", duration_days=2,
                       features=(FeatureSpec("training.create"),),
                       description="Создать поток или использовать существующий. Добавить обучающегося в заявку потока."),
            ActionSpec(name="Подтвердить оплату и зачисление", duration_days=5,
                       after=("Организовать поток обучения",),
                       description="Проверить оплату в заявке потока, вручную или через импорт оплат. Затем завершить действие.",
                       outcomes=(OutcomeSpec(code="done", name="Оплата и зачисление подтверждены",
                                             is_comment_required=True),)),
        )),
        StageSpec(name="Прохождение курса", type=StageInstanceContextType.PROGRAM,
                  after=("Зачисление и оплата",), actions=(
            ActionSpec(name="Предоставить доступ к курсу", duration_days=1,
                       description="Передать обучающемуся расписание и данные доступа к учебной платформе."),
            ActionSpec(name="Завершить обучение и аттестацию", duration_days=60,
                       after=("Предоставить доступ к курсу",),
                       description="Проверить результаты обучения в потоке и зафиксировать итог аттестации.",
                       outcomes=(OutcomeSpec(code="done", name="Обучение завершено", is_comment_required=True),)),
        )),
        StageSpec(name="Итоги и обратная связь", after=("Прохождение курса",), actions=(
            ActionSpec(name="Передать итоговые документы", duration_days=5,
                       description="Проверить выдачу документа по результатам обучения и зафиксировать реквизиты в комментарии.",
                       outcomes=(OutcomeSpec(code="done", name="Документы переданы", is_comment_required=True),)),
            ActionSpec(name="Получить обратную связь клиента", duration_days=3,
                       after=("Передать итоговые документы",),
                       outcomes=(OutcomeSpec(code="done", name="Обратная связь получена", is_comment_required=True),)),
        )),
    ),
)
