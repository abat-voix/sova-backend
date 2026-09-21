from datetime import timedelta

from sova.interactions.tests.factories import InteractionProductFactory
from sova.processes.models import ActionInstance
from sova.processes.tests.base import PRODUCT, EngineTestCase
from sova.workflows.tests.factories import ActionDependencyFactory, StageTransitionFactory


class PlannerTest(EngineTestCase):
    """Плановые даты, которые планировщик проставляет при запуске процесса."""

    def test_action_is_planned_from_the_start_of_the_process(self) -> None:
        """Действие первого этапа планируется от момента запуска процесса."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "А", duration_days=3)

        process = self.start()

        instance = self.action_instance(process, action)
        # Проверяем, что план отсчитан от запуска: тот же момент, что и фактическое начало
        self.assertEqual(instance.planned_start, instance.actual_start)
        self.assertEqual(instance.planned_end - instance.planned_start, timedelta(days=3))

    def test_action_without_duration_is_planned_for_one_day(self) -> None:
        """Действие без длительности в шаблоне планируется на сутки."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "А")

        process = self.start()

        instance = self.action_instance(process, action)
        # Проверяем длительность по умолчанию
        self.assertEqual(instance.planned_end - instance.planned_start, timedelta(days=1))

    def test_pending_action_of_a_later_stage_is_planned_too(self) -> None:
        """План есть и у действия этапа, до которого очередь ещё не дошла."""
        first = self.builder.stage("Первый")
        self.builder.action(first, "А")
        second = self.builder.stage("Второй", after=(first,))
        later = self.builder.action(second, "Б")

        process = self.start()

        # Проверяем, что ожидающее действие спланировано
        self.assertIsNotNone(self.action_instance(process, later).planned_start)

    def test_next_stage_starts_when_the_previous_one_ends(self) -> None:
        """Этап начинается там, где заканчивается предшественник: по последнему его действию."""
        first = self.builder.stage("Первый")
        early = self.builder.action(first, "А", duration_days=2)
        late = self.builder.action(first, "Б", duration_days=5)
        second = self.builder.stage("Второй", after=(first,))
        following = self.builder.action(second, "В", duration_days=1)

        process = self.start()

        # Проверяем, что взят конец последнего действия, а не первого
        self.assertEqual(
            self.action_instance(process, following).planned_start,
            self.action_instance(process, late).planned_end,
        )
        self.assertGreater(
            self.action_instance(process, following).planned_start,
            self.action_instance(process, early).planned_end,
        )

    def test_stage_with_several_predecessors_waits_for_the_last_one(self) -> None:
        """Этап с несколькими предшественниками начинается после самого позднего."""
        short = self.builder.stage("Короткий")
        self.builder.action(short, "А", duration_days=1)
        long_stage = self.builder.stage("Долгий")
        slow = self.builder.action(long_stage, "Б", duration_days=7)
        joint = self.builder.stage("Общий", after=(short, long_stage))
        after_both = self.builder.action(joint, "В")

        process = self.start()

        # Проверяем, что взят максимум по предшественникам
        self.assertEqual(
            self.action_instance(process, after_both).planned_start,
            self.action_instance(process, slow).planned_end,
        )

    def test_plan_of_every_action_is_filled_and_consistent(self) -> None:
        """Инвариант: план есть у всех действий и не выворачивается наизнанку."""
        first = self.builder.stage("Первый")
        self.builder.action(first, "А", duration_days=2)
        second = self.builder.stage("Второй", after=(first,))
        self.builder.action(second, "Б", duration_days=3)
        third = self.builder.stage("Третий", after=(second,))
        self.builder.action(third, "В")

        process = self.start()

        instances = ActionInstance.objects.filter(stage_instance__workflow_instance=process)
        # Проверяем инварианты на всех действиях процесса
        self.assertEqual(instances.count(), 3)
        for instance in instances:
            self.assertIsNotNone(instance.planned_start)
            self.assertIsNotNone(instance.planned_end)
            self.assertGreaterEqual(instance.planned_end, instance.planned_start)

    def test_dependent_action_starts_after_its_prerequisite(self) -> None:
        """Действие с зависимостью начинается, когда заканчивается предусловие."""
        stage = self.builder.stage("Первый")
        first = self.builder.action(stage, "А", duration_days=4)
        second = self.builder.action(stage, "Б", after=(first,), duration_days=2)

        process = self.start()

        # Проверяем инвариант: зависимое не раньше предусловия
        self.assertEqual(
            self.action_instance(process, second).planned_start,
            self.action_instance(process, first).planned_end,
        )

    def test_independent_actions_of_a_stage_start_together(self) -> None:
        """Действия без зависимостей начинаются вместе с этапом."""
        stage = self.builder.stage("Первый")
        one = self.builder.action(stage, "А", duration_days=4)
        two = self.builder.action(stage, "Б", duration_days=2)

        process = self.start()

        # Проверяем параллельность
        self.assertEqual(
            self.action_instance(process, one).planned_start,
            self.action_instance(process, two).planned_start,
        )

    def test_transition_only_action_is_planned_from_its_source(self) -> None:
        """Действие «только по переходу» планируется от конца действия-источника."""
        stage = self.builder.stage("Первый")
        source = self.builder.action(stage, "А", duration_days=3)
        target = self.builder.action(stage, "Б", trigger_only=True, duration_days=1)
        self.builder.branch(source.action_outcomes.get(code="done"), target)

        process = self.start()

        # Проверяем, что взят конец источника, а не начало этапа
        self.assertEqual(
            self.action_instance(process, target).planned_start,
            self.action_instance(process, source).planned_end,
        )

    def test_transition_only_action_ignores_a_source_from_another_stage(self) -> None:
        """Источник перехода из другого этапа игнорируется — как и в движке."""
        first = self.builder.stage("Первый")
        source = self.builder.action(first, "А", duration_days=3)
        longest = self.builder.action(first, "В", duration_days=9)
        second = self.builder.stage("Второй", after=(first,))
        target = self.builder.action(second, "Б", trigger_only=True, duration_days=1)
        self.builder.branch(source.action_outcomes.get(code="done"), target)

        process = self.start()

        # Проверяем, что действие начинается вместе со своим этапом, а не от источника
        self.assertEqual(
            self.action_instance(process, target).planned_start,
            self.action_instance(process, longest).planned_end,
        )

    def test_product_stage_starts_after_the_linked_interaction_stage(self) -> None:
        """Этап продукта начинается в конце связанного этапа взаимодействия."""
        common = self.builder.stage("Общий")
        common_action = self.builder.action(common, "А", duration_days=4)
        product_stage = self.builder.stage("Продуктовый", after=(common,), type=PRODUCT)
        product_action = self.builder.action(product_stage, "Б", duration_days=2)
        product = InteractionProductFactory(interaction=self.interaction)

        process = self.start()

        # Проверяем, что план продукта пристыкован к общему этапу
        self.assertEqual(
            self.action_instance(process, product_action, product).planned_start,
            self.action_instance(process, common_action).planned_end,
        )

    def test_product_added_after_the_start_is_planned_from_the_linked_stage(self) -> None:
        """Продукт, заведённый позже, считается от планового конца связанного этапа, а не от «сейчас»."""
        common = self.builder.stage("Общий")
        common_action = self.builder.action(common, "А", duration_days=4)
        product_stage = self.builder.stage("Продуктовый", after=(common,), type=PRODUCT)
        product_action = self.builder.action(product_stage, "Б", duration_days=2)

        process = self.start()
        product = InteractionProductFactory(interaction=self.interaction)
        self.complete(process, common_action)

        # Проверяем, что план новой группы не привязан к моменту её появления
        self.assertEqual(
            self.action_instance(process, product_action, product).planned_start,
            self.action_instance(process, common_action).planned_end,
        )

    def test_repeated_execution_is_planned_after_the_rollback(self) -> None:
        """Новое исполнение после отката получает план, а не остаётся без дат."""
        first = self.builder.stage("Первый")
        one = self.builder.action(first, "А", duration_days=2)
        second = self.builder.stage("Второй", after=(first,))
        two = self.builder.action(second, "Б", duration_days=2)

        process = self.start()
        self.complete(process, one)
        self.complete(process, two)
        self.cancel(process, second)

        repeated = self.action_instance(process, two)
        # Проверяем, что повтор спланирован
        self.assertEqual(repeated.execution_no, 2)
        self.assertIsNotNone(repeated.planned_start)
        self.assertIsNotNone(repeated.planned_end)

    def test_completed_action_keeps_its_baseline_plan(self) -> None:
        """Выполненное действие планировщик не трогает: базовый план неизменен."""
        stage = self.builder.stage("Первый")
        action = self.builder.action(stage, "А", duration_days=2)
        second = self.builder.stage("Второй", after=(stage,))
        self.builder.action(second, "Б")

        process = self.start()
        before = self.action_instance(process, action).planned_end
        self.complete(process, action)

        # Проверяем, что завершение не сдвинуло план
        self.assertEqual(self.action_instance(process, action).planned_end, before)

    def test_cycle_between_stages_does_not_hang_the_calculation(self) -> None:
        """Возвратная связь между этапами не зацикливает расчёт."""
        first = self.builder.stage("Первый")
        one = self.builder.action(first, "А")
        second = self.builder.stage("Второй", after=(first,))
        two = self.builder.action(second, "Б")
        StageTransitionFactory(from_stage=second, to_stage=first)

        process = self.start()

        # Проверяем, что расчёт завершился и план есть у обоих
        self.assertIsNotNone(self.action_instance(process, one).planned_start)
        self.assertIsNotNone(self.action_instance(process, two).planned_start)

    def test_cycle_between_actions_does_not_hang_the_calculation(self) -> None:
        """Взаимная зависимость действий внутри этапа не зацикливает расчёт."""
        stage = self.builder.stage("Первый")
        one = self.builder.action(stage, "А")
        two = self.builder.action(stage, "Б", after=(one,))
        ActionDependencyFactory(action=one, depends_on_action=two)

        process = self.start()

        # Проверяем, что расчёт завершился
        self.assertIsNotNone(self.action_instance(process, one).planned_start)
        self.assertIsNotNone(self.action_instance(process, two).planned_start)

    def test_stage_without_actions_does_not_shift_the_next_one(self) -> None:
        """Этап без действий имеет нулевую длительность."""
        first = self.builder.stage("Первый")
        one = self.builder.action(first, "А", duration_days=3)
        empty = self.builder.stage("Пустой", after=(first,))
        third = self.builder.stage("Третий", after=(empty,))
        last = self.builder.action(third, "Б")

        process = self.start()

        # Проверяем, что пустой этап не добавил времени
        self.assertEqual(
            self.action_instance(process, last).planned_start,
            self.action_instance(process, one).planned_end,
        )
