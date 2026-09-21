from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.processes.enum import StageInstanceContextType
from sova.workflows.enum import Audience, WorkflowChangeType
from sova.workflows.models import (
    ActionDependency,
    ActionOutcome,
    ActionTransition,
    StageTransition,
    Workflow,
    WorkflowAction,
    WorkflowChange,
    WorkflowStage,
)
from sova.workflows.schemas import ActionSpec, OutcomeSpec, StageSpec, WorkflowSpec
from sova.workflows.services import WorkflowTemplateError, workflow_template_service


class WorkflowTemplateServiceStageTest(TestCase):
    """Тесты сборки шаблона: сам workflow, его этапы и связи между ними."""

    def test_create_creates_workflow_from_spec(self) -> None:
        """Поля workflow берутся из декларации, базовым он становится только по требованию."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            audience=Audience.B2B,
            description="Процесс работы с вузом",
            stale_threshold_days=180,
            stages=(StageSpec(name="Контакт"),),
        )

        workflow = workflow_template_service.create(spec=spec)

        # Проверяем поля шаблона
        self.assertEqual(workflow.code, "base-b2b")
        self.assertEqual(workflow.name, "Базовый процесс")
        self.assertEqual(workflow.audience, Audience.B2B)
        self.assertEqual(workflow.description, "Процесс работы с вузом")
        self.assertEqual(workflow.stale_threshold_days, 180)
        self.assertTrue(workflow.is_active)
        self.assertFalse(workflow.is_base)

    def test_create_marks_workflow_as_base_on_request(self) -> None:
        """Флаг `is_base` задаётся вызывающим, а не декларацией."""
        spec = WorkflowSpec(code="base-b2b", name="Базовый процесс", stages=(StageSpec(name="Контакт"),))

        workflow = workflow_template_service.create(spec=spec, is_base=True)

        # Проверяем, что шаблон стал базовым для аудитории
        self.assertTrue(workflow.is_base)

    def test_create_numbers_stages_in_declaration_order(self) -> None:
        """Этапы получают `sort_order` по порядку объявления."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(
                StageSpec(name="Контакт"),
                StageSpec(name="Документы"),
                StageSpec(name="Поставка", type=StageInstanceContextType.PRODUCT),
            ),
        )

        workflow = workflow_template_service.create(spec=spec)

        # Проверяем порядок и типы этапов
        stages = WorkflowStage.objects.filter(workflow=workflow).order_by("sort_order")
        self.assertEqual(
            [(stage.name, stage.sort_order, stage.type) for stage in stages],
            [
                ("Контакт", 1, StageInstanceContextType.INTERACTION),
                ("Документы", 2, StageInstanceContextType.INTERACTION),
                ("Поставка", 3, StageInstanceContextType.PRODUCT),
            ],
        )

    def test_create_marks_first_stage_initial_and_last_final(self) -> None:
        """Точки входа и выхода помечаются флагами, а не выводятся из графа."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(
                StageSpec(name="Контакт"),
                StageSpec(name="Документы", after=("Контакт",)),
                StageSpec(name="Сопровождение", after=("Документы",)),
            ),
        )

        workflow = workflow_template_service.create(spec=spec)

        # Проверяем флаги начального и финального этапов
        stages = {stage.name: stage for stage in WorkflowStage.objects.filter(workflow=workflow)}
        self.assertTrue(stages["Контакт"].is_initial)
        self.assertFalse(stages["Документы"].is_initial)
        self.assertTrue(stages["Сопровождение"].is_final)
        self.assertFalse(stages["Документы"].is_final)

    def test_create_links_stages_by_name(self) -> None:
        """Связи этапов собираются по именам из `after`."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(
                StageSpec(name="Контакт"),
                StageSpec(name="Поставка", type=StageInstanceContextType.PRODUCT, after=("Контакт",)),
                StageSpec(name="Обучение", type=StageInstanceContextType.PROGRAM, after=("Контакт",)),
                StageSpec(name="Сопровождение", after=("Поставка", "Обучение")),
            ),
        )

        workflow = workflow_template_service.create(spec=spec)

        # Проверяем рёбра графа этапов
        transitions = StageTransition.objects.filter(from_stage__workflow=workflow)
        self.assertEqual(
            sorted((item.from_stage.name, item.to_stage.name) for item in transitions),
            [
                ("Контакт", "Обучение"),
                ("Контакт", "Поставка"),
                ("Обучение", "Сопровождение"),
                ("Поставка", "Сопровождение"),
            ],
        )

    def test_create_rejects_unknown_stage_name(self) -> None:
        """Опечатка в имени этапа-источника останавливает сборку до записи в базу."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(StageSpec(name="Контакт"), StageSpec(name="Документы", after=("Контак",))),
        )

        with self.assertRaisesMessage(WorkflowTemplateError, "Контак"):
            workflow_template_service.create(spec=spec)

        # Проверяем, что шаблон не остался в базе
        self.assertFalse(Workflow.objects.filter(code="base-b2b").exists())


class WorkflowTemplateServiceActionTest(TestCase):
    """Тесты сборки действий этапа: порядок, исходы, зависимости и переходы."""

    def create(self, *actions: ActionSpec, second_stage: StageSpec | None = None) -> Workflow:
        """Собирает шаблон с одним этапом «Документы» и переданными действиями."""
        stages = [StageSpec(name="Документы", actions=actions)]
        if second_stage is not None:
            stages.append(second_stage)
        return workflow_template_service.create(
            spec=WorkflowSpec(code="base-b2b", name="Базовый процесс", stages=tuple(stages)),
        )

    def test_create_numbers_actions_within_stage(self) -> None:
        """Действия нумеруются по порядку объявления внутри своего этапа."""
        workflow = self.create(
            ActionSpec(name="Подготовить документы"),
            ActionSpec(name="Согласовать документы"),
            second_stage=StageSpec(name="Поставка", actions=(ActionSpec(name="Передать лицензию"),)),
        )

        # Проверяем нумерацию: у каждого этапа она своя
        actions = WorkflowAction.objects.filter(stage__workflow=workflow).order_by("stage__sort_order", "sort_order")
        self.assertEqual(
            [(action.stage.name, action.name, action.sort_order) for action in actions],
            [
                ("Документы", "Подготовить документы", 1),
                ("Документы", "Согласовать документы", 2),
                ("Поставка", "Передать лицензию", 1),
            ],
        )

    def test_create_copies_action_fields_from_spec(self) -> None:
        """Поля действия берутся из декларации."""
        self.create(
            ActionSpec(
                name="Доработать документы",
                description="После правок вуза",
                duration_days=3,
                is_optional=True,
                is_trigger_only=True,
            ),
        )

        action = WorkflowAction.objects.get(name="Доработать документы")
        # Проверяем поля действия
        self.assertEqual(action.description, "После правок вуза")
        self.assertEqual(action.default_duration_days, 3)
        self.assertTrue(action.is_optional)
        self.assertTrue(action.is_trigger_only)

    def test_create_adds_default_outcome_to_action_without_outcomes(self) -> None:
        """Действию без объявленных исходов добавляется «Выполнено» — иначе его нельзя завершить."""
        self.create(ActionSpec(name="Подготовить документы"))

        outcomes = ActionOutcome.objects.filter(action__name="Подготовить документы")
        # Проверяем исход по умолчанию
        self.assertEqual([(outcome.code, outcome.name) for outcome in outcomes], [("done", "Выполнено")])

    def test_create_adds_declared_outcomes_with_their_rules(self) -> None:
        """Объявленные исходы создаются со своими правилами комментария и вложения."""
        self.create(
            ActionSpec(
                name="Согласовать документы",
                outcomes=(
                    OutcomeSpec(code="done", name="Согласовано", is_attachment_required=True),
                    OutcomeSpec(code="revision", name="Нужны правки", is_comment_required=True),
                ),
            ),
        )

        outcomes = ActionOutcome.objects.filter(action__name="Согласовать документы").order_by("code")
        # Проверяем исходы и их правила
        self.assertEqual(
            [
                (outcome.code, outcome.name, outcome.is_comment_required, outcome.is_attachment_required)
                for outcome in outcomes
            ],
            [("done", "Согласовано", False, True), ("revision", "Нужны правки", True, False)],
        )

    def test_create_links_dependencies_by_name(self) -> None:
        """Зависимости действий собираются по именам из `after`."""
        self.create(
            ActionSpec(name="Подготовить документы"),
            ActionSpec(name="Согласовать документы", after=("Подготовить документы",)),
        )

        dependencies = ActionDependency.objects.all()
        # Проверяем рёбра графа зависимостей
        self.assertEqual(
            [(item.action.name, item.depends_on_action.name) for item in dependencies],
            [("Согласовать документы", "Подготовить документы")],
        )

    def test_create_links_transition_from_outcome(self) -> None:
        """Исход с `starts` запускает указанное действие того же этапа."""
        self.create(
            ActionSpec(
                name="Согласовать документы",
                outcomes=(
                    OutcomeSpec(code="done", name="Согласовано"),
                    OutcomeSpec(code="revision", name="Нужны правки", starts="Доработать документы"),
                ),
            ),
            ActionSpec(name="Доработать документы", is_trigger_only=True),
        )

        transitions = ActionTransition.objects.all()
        # Проверяем переход по исходу
        self.assertEqual(
            [(item.outcome.code, item.target_action.name) for item in transitions],
            [("revision", "Доработать документы")],
        )

    def test_create_rejects_dependency_on_action_of_another_stage(self) -> None:
        """Зависимость между этапами запрещена: порядок этапов задают только связи этапов."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(
                StageSpec(name="Документы", actions=(ActionSpec(name="Подписать договор"),)),
                StageSpec(
                    name="Поставка",
                    actions=(ActionSpec(name="Передать лицензию", after=("Подписать договор",)),),
                ),
            ),
        )

        with self.assertRaisesMessage(WorkflowTemplateError, "Подписать договор"):
            workflow_template_service.create(spec=spec)

        # Проверяем, что шаблон не остался в базе
        self.assertFalse(Workflow.objects.filter(code="base-b2b").exists())

    def test_create_rejects_mandatory_action_depending_on_optional(self) -> None:
        """Обязательное действие не может зависеть от необязательного: его могут не выполнить."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(
                StageSpec(
                    name="Документы",
                    actions=(
                        ActionSpec(name="Провести встречу", is_optional=True),
                        ActionSpec(name="Подписать договор", after=("Провести встречу",)),
                    ),
                ),
            ),
        )

        with self.assertRaisesMessage(WorkflowTemplateError, "необязательного"):
            workflow_template_service.create(spec=spec)

    def test_create_rejects_dependency_cycle(self) -> None:
        """Взаимные зависимости сделали бы действия невыполнимыми."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(
                StageSpec(
                    name="Документы",
                    actions=(
                        ActionSpec(name="Подготовить документы", after=("Согласовать документы",)),
                        ActionSpec(name="Согласовать документы", after=("Подготовить документы",)),
                    ),
                ),
            ),
        )

        with self.assertRaisesMessage(WorkflowTemplateError, "цикл"):
            workflow_template_service.create(spec=spec)

    def test_create_rejects_transition_to_action_of_another_stage(self) -> None:
        """Переход по исходу ведёт только на действие того же этапа."""
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(
                StageSpec(
                    name="Документы",
                    actions=(
                        ActionSpec(
                            name="Согласовать документы",
                            outcomes=(OutcomeSpec(code="revision", name="Нужны правки", starts="Установить ПО"),),
                        ),
                    ),
                ),
                StageSpec(name="Поставка", actions=(ActionSpec(name="Установить ПО"),)),
            ),
        )

        with self.assertRaisesMessage(WorkflowTemplateError, "Установить ПО"):
            workflow_template_service.create(spec=spec)


class WorkflowTemplateServiceAuditTest(TestCase):
    """Тесты аудита: сборка шаблона журналируется так же, как создание через API."""

    def test_create_records_every_entity_in_audit(self) -> None:
        """Каждая созданная сущность шаблона попадает в журнал изменений от имени автора."""
        user = UserFactory()
        spec = WorkflowSpec(
            code="base-b2b",
            name="Базовый процесс",
            stages=(
                StageSpec(name="Документы", actions=(ActionSpec(name="Подготовить документы"),)),
                StageSpec(
                    name="Поставка",
                    after=("Документы",),
                    actions=(
                        ActionSpec(
                            name="Передать лицензию",
                            outcomes=(
                                OutcomeSpec(code="done", name="Передано"),
                                OutcomeSpec(code="blocked", name="Нет лицензии", starts="Запросить лицензию"),
                            ),
                        ),
                        ActionSpec(
                            name="Запросить лицензию",
                            is_trigger_only=True,
                            after=("Передать лицензию",),
                        ),
                    ),
                ),
            ),
        )

        workflow = workflow_template_service.create(spec=spec, created_by=user)

        changes = WorkflowChange.objects.filter(workflow=workflow)
        # Проверяем, что журнал знает автора и тип изменения
        self.assertEqual({change.created_by for change in changes}, {user})
        self.assertEqual({change.change_type for change in changes}, {WorkflowChangeType.CREATED})
        # Проверяем, что журнал покрывает все сущности шаблона
        counts: dict[str, int] = {}
        for change in changes:
            counts[change.entity_type] = counts.get(change.entity_type, 0) + 1
        self.assertEqual(
            counts,
            {
                "workflow": 1,
                "workflowstage": 2,
                "stagetransition": 1,
                "workflowaction": 3,
                "actionoutcome": 4,
                "actiondependency": 1,
                "actiontransition": 1,
            },
        )

    def test_create_without_author_leaves_audit_anonymous(self) -> None:
        """Без пользователя журнал пишется без автора: команду запускают и из консоли."""
        spec = WorkflowSpec(code="base-b2b", name="Базовый процесс", stages=(StageSpec(name="Документы"),))

        workflow = workflow_template_service.create(spec=spec)

        # Проверяем, что записи есть и автор не указан
        changes = WorkflowChange.objects.filter(workflow=workflow)
        self.assertTrue(changes.exists())
        self.assertEqual({change.created_by for change in changes}, {None})
