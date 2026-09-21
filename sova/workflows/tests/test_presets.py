from django.test import TestCase

from sova.core.tests.factories import UserFactory
from sova.interactions.tests.factories import (
    InteractionFactory,
    InteractionProductFactory,
    InteractionProgramFactory,
)
from sova.processes.enum import (
    ActionInstanceStatus,
    StageInstanceContextType,
    StageInstanceStatus,
    WorkflowInstanceStatus,
)
from sova.processes.models import ActionInstance, StageInstance
from sova.processes.services import workflow_engine_service
from sova.workflows.models import ActionOutcome, WorkflowAction
from sova.workflows.presets import BASE_B2B_PRESET
from sova.workflows.services import workflow_template_service


class BaseB2BPresetTest(TestCase):
    """Тесты декларации базового процесса работы с вузом."""

    def test_preset_declares_business_stages_in_order(self) -> None:
        """Этапы идут по бизнес-порядку, поставка и обучение размножаются по продуктам и программам."""
        # Проверяем состав и типы этапов
        self.assertEqual(
            [(stage.name, stage.type) for stage in BASE_B2B_PRESET.stages],
            [
                ("Подготовка и контакт", StageInstanceContextType.INTERACTION),
                ("Согласование и документы", StageInstanceContextType.INTERACTION),
                ("Поставка ПО", StageInstanceContextType.PRODUCT),
                ("Обучение преподавателей", StageInstanceContextType.PROGRAM),
                ("Сопровождение", StageInstanceContextType.INTERACTION),
            ],
        )

    def test_preset_chains_stages_one_after_another(self) -> None:
        """Каждый следующий этап открывается после закрытия предыдущего."""
        # Проверяем цепочку связей: первый этап без входящих связей
        self.assertEqual(
            [(stage.name, stage.after) for stage in BASE_B2B_PRESET.stages],
            [
                ("Подготовка и контакт", ()),
                ("Согласование и документы", ("Подготовка и контакт",)),
                ("Поставка ПО", ("Согласование и документы",)),
                ("Обучение преподавателей", ("Поставка ПО",)),
                ("Сопровождение", ("Обучение преподавателей",)),
            ],
        )

    def test_preset_reworks_documents_by_transition(self) -> None:
        """Исход «Нужны правки» запускает доработку, которая сама по себе не стартует."""
        actions = {action.name: action for stage in BASE_B2B_PRESET.stages for action in stage.actions}
        revision = next(
            outcome for outcome in actions["Согласовать документы"].outcomes if outcome.starts is not None
        )

        # Проверяем ветвление и то, что доработка ждёт перехода
        self.assertEqual(revision.starts, "Доработать документы")
        self.assertTrue(revision.is_comment_required)
        self.assertTrue(actions["Доработать документы"].is_trigger_only)

    def test_preset_plans_duration_for_every_action(self) -> None:
        """У каждого действия задана плановая длительность — без неё нет ни плана, ни контроля зависания."""
        actions = [action for stage in BASE_B2B_PRESET.stages for action in stage.actions]

        # Проверяем, что длительность задана всем действиям
        self.assertEqual([action.name for action in actions if action.duration_days is None], [])


class BaseB2BPresetProcessTest(TestCase):
    """Тесты запускаемости базового процесса: собранный шаблон проходит движком от старта до конца."""

    def setUp(self) -> None:
        """Собирает шаблон из пресета и взаимодействие с вузом, продуктом и программой."""
        self.user = UserFactory()
        self.workflow = workflow_template_service.create(spec=BASE_B2B_PRESET, created_by=self.user)
        self.interaction = InteractionFactory()
        self.product = InteractionProductFactory(interaction=self.interaction)
        self.program = InteractionProgramFactory(interaction=self.interaction)

    def action(self, name: str) -> WorkflowAction:
        """Действие шаблона по имени."""
        return WorkflowAction.objects.get(stage__workflow=self.workflow, name=name)

    def action_instances(self, process, name: str):
        """Экземпляры действия в процессе, свежие сначала."""
        return ActionInstance.objects.filter(
            stage_instance__workflow_instance=process,
            action=self.action(name),
        ).order_by("-execution_no")

    def complete(self, process, name: str, code: str = "done") -> None:
        """Завершает все действующие экземпляры действия с исходом по коду."""
        outcome = ActionOutcome.objects.get(action=self.action(name), code=code)
        for instance in self.action_instances(process, name).filter(status=ActionInstanceStatus.IN_PROGRESS):
            workflow_engine_service.complete_action(
                action_instance=instance,
                outcome=outcome,
                comment="Готово",
                completed_by=self.user,
            )

    def test_start_opens_first_stage_and_its_first_action(self) -> None:
        """Запуск открывает начальный этап: первое действие в работе, зависимое ждёт."""
        process = workflow_engine_service.start(
            workflow=self.workflow,
            interaction=self.interaction,
            started_by=self.user,
        )

        # Проверяем, что процесс идёт и начальный этап открыт
        self.assertEqual(process.status, WorkflowInstanceStatus.RUNNING)
        first_stage = StageInstance.objects.get(
            workflow_instance=process,
            stage__name="Подготовка и контакт",
        )
        self.assertEqual(first_stage.status, StageInstanceStatus.IN_PROGRESS)
        # Проверяем статусы действий начального этапа
        self.assertEqual(
            self.action_instances(process, "Найти контакт").first().status,
            ActionInstanceStatus.IN_PROGRESS,
        )
        self.assertEqual(
            self.action_instances(process, "Связаться с вузом").first().status,
            ActionInstanceStatus.PENDING,
        )

    def test_start_creates_stage_instance_per_product_and_program(self) -> None:
        """Этапы поставки и обучения создаются на каждый продукт и каждую программу взаимодействия."""
        second_product = InteractionProductFactory(interaction=self.interaction)

        process = workflow_engine_service.start(
            workflow=self.workflow,
            interaction=self.interaction,
            started_by=self.user,
        )

        # Проверяем контексты экземпляров этапа поставки
        self.assertEqual(
            set(
                StageInstance.objects.filter(
                    workflow_instance=process,
                    stage__name="Поставка ПО",
                ).values_list("context_id", flat=True),
            ),
            {self.product.pk, second_product.pk},
        )
        # Проверяем контекст экземпляра этапа обучения
        self.assertEqual(
            set(
                StageInstance.objects.filter(
                    workflow_instance=process,
                    stage__name="Обучение преподавателей",
                ).values_list("context_id", flat=True),
            ),
            {self.program.pk},
        )

    def test_process_completes_when_all_actions_are_done(self) -> None:
        """Процесс по шаблону доходит до конца: все обязательные действия выполнимы по порядку."""
        process = workflow_engine_service.start(
            workflow=self.workflow,
            interaction=self.interaction,
            started_by=self.user,
        )

        for name in (
            "Найти контакт",
            "Связаться с вузом",
            "Провести встречу",
            "Подготовить документы",
            "Согласовать документы",
            "Подписать договор",
            "Передать лицензию",
            "Установить ПО",
            "Обучить преподавателей",
            "Обновить образовательную программу",
            "Проверить результат",
        ):
            self.complete(process, name)

        process.refresh_from_db()
        # Проверяем, что процесс завершён и незакрытых этапов не осталось
        self.assertEqual(process.status, WorkflowInstanceStatus.COMPLETED)
        self.assertEqual(
            list(
                StageInstance.objects.filter(workflow_instance=process)
                .exclude(status=StageInstanceStatus.COMPLETED)
                .values_list("stage__name", flat=True),
            ),
            [],
        )

    def test_revision_outcome_starts_rework_action(self) -> None:
        """Исход «Нужны правки» запускает доработку документов, не закрывая этап."""
        process = workflow_engine_service.start(
            workflow=self.workflow,
            interaction=self.interaction,
            started_by=self.user,
        )
        for name in ("Найти контакт", "Связаться с вузом", "Провести встречу", "Подготовить документы"):
            self.complete(process, name)

        self.complete(process, "Согласовать документы", code="revision")

        # Проверяем, что доработка стартовала, а этап остался открытым
        self.assertEqual(
            self.action_instances(process, "Доработать документы").first().status,
            ActionInstanceStatus.IN_PROGRESS,
        )
        self.assertEqual(
            StageInstance.objects.get(
                workflow_instance=process,
                stage__name="Согласование и документы",
            ).status,
            StageInstanceStatus.IN_PROGRESS,
        )
