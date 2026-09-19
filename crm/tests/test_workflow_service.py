from django.test import TestCase
from rest_framework.exceptions import PermissionDenied

from crm.models import InstanceChecklistProgress, InteractionProductStatus, TransitionLog, WorkflowTransition
from crm.services.checklist import ChecklistService
from crm.services.interaction_product_status import InteractionProductStatusService
from crm.services.workflow import (
    ChecklistNotCompleteError,
    CommentRequiredError,
    ProductsNotCompleteError,
    TransitionNotAllowedError,
    WorkflowService,
)
from crm.tests.factories import (
    InteractionFactory,
    InteractionProductFactory,
    ResponsibleAssignmentFactory,
    StatusChecklistItemFactory,
    UniversityFactory,
    UserFactory,
    WorkflowInstanceFactory,
    WorkflowStatusFactory,
    WorkflowTemplateFactory,
    WorkflowTransitionFactory,
)


class WorkflowServiceTransitionTestCase(TestCase):
    """Тесты WorkflowService.transition."""

    def setUp(self) -> None:
        """Готовит шаблон A->B, сделку с назначенным КАМом и процесс на статусе A."""
        self.template = WorkflowTemplateFactory()
        self.status_a = WorkflowStatusFactory(template=self.template, order=1, is_initial=True)
        self.status_b = WorkflowStatusFactory(template=self.template, order=2)
        self.transition_ab = WorkflowTransitionFactory(
            template=self.template, from_status=self.status_a, to_status=self.status_b,
        )

        self.manager = UserFactory()
        self.university = UniversityFactory()
        ResponsibleAssignmentFactory(university=self.university, manager=self.manager)
        self.interaction = InteractionFactory(university=self.university)
        self.instance = WorkflowInstanceFactory(
            interaction=self.interaction, template=self.template, current_status=self.status_a,
        )

    def test_successful_transition_creates_log_and_moves_status(self) -> None:
        """Успешный переход создаёт TransitionLog и обновляет current_status заявки."""
        log = WorkflowService(self.instance).transition(self.status_b.id, self.manager, comment="Готово")

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_status_id, self.status_b.id)
        self.assertIsInstance(log, TransitionLog)
        self.assertEqual(log.from_status_id, self.status_a.id)
        self.assertEqual(log.to_status_id, self.status_b.id)
        self.assertEqual(log.comment, "Готово")

    def test_creates_checklist_progress_for_new_status(self) -> None:
        """После перехода лениво создаётся прогресс чек-листа нового статуса."""
        item = StatusChecklistItemFactory(status=self.status_b)

        WorkflowService(self.instance).transition(self.status_b.id, self.manager)

        self.assertTrue(
            InstanceChecklistProgress.objects.filter(instance=self.instance, checklist_item=item).exists(),
        )

    def test_raises_when_no_such_transition(self) -> None:
        """Переход, не описанный ребром графа, отклоняется."""
        other_status = WorkflowStatusFactory(template=self.template, order=3)

        with self.assertRaises(TransitionNotAllowedError):
            WorkflowService(self.instance).transition(other_status.id, self.manager)

    def test_raises_permission_denied_for_unassigned_user(self) -> None:
        """Пользователь, не являющийся КАМом вуза сделки и без права, отклоняется."""
        with self.assertRaises(PermissionDenied):
            WorkflowService(self.instance).transition(self.status_b.id, UserFactory())

    def test_raises_when_required_permission_missing(self) -> None:
        """
        required_permission на конкретном переходе проверяется отдельно от общего доступа к workflow.

        Назначенный КАМ проходит общий гейт workflow.transition, но не имеет
        конкретного crm.can_transition_backward — переход должен быть отклонён.
        """
        self.transition_ab.required_permission = "crm.can_transition_backward"
        self.transition_ab.save(update_fields=["required_permission"])

        with self.assertRaises(PermissionDenied):
            WorkflowService(self.instance).transition(self.status_b.id, self.manager)

    def test_raises_when_comment_required_but_missing(self) -> None:
        """requires_comment=True без переданного комментария отклоняется."""
        self.transition_ab.requires_comment = True
        self.transition_ab.save(update_fields=["requires_comment"])

        with self.assertRaises(CommentRequiredError):
            WorkflowService(self.instance).transition(self.status_b.id, self.manager, comment="")

    def test_raises_when_checklist_not_complete(self) -> None:
        """requires_checklist_complete=True блокирует переход, пока не все пункты отмечены."""
        StatusChecklistItemFactory(status=self.status_a)
        self.transition_ab.requires_checklist_complete = True
        self.transition_ab.save(update_fields=["requires_checklist_complete"])

        with self.assertRaises(ChecklistNotCompleteError):
            WorkflowService(self.instance).transition(self.status_b.id, self.manager)

    def test_allows_transition_once_checklist_complete(self) -> None:
        """После отметки всех пунктов чек-листа переход с requires_checklist_complete проходит."""
        item = StatusChecklistItemFactory(status=self.status_a)
        self.transition_ab.requires_checklist_complete = True
        self.transition_ab.save(update_fields=["requires_checklist_complete"])
        ChecklistService.toggle(self.instance, item.id, self.manager, is_done=True)

        log = WorkflowService(self.instance).transition(self.status_b.id, self.manager)

        self.assertEqual(log.to_status_id, self.status_b.id)

    def test_raises_when_products_not_complete(self) -> None:
        """requires_all_products_complete=True блокирует переход, пока продукт не дошёл до финального подстатуса."""
        WorkflowStatusFactory(template=self.template, parent=self.status_a, order=1, is_initial=True)
        InteractionProductFactory(interaction=self.interaction)
        self.transition_ab.requires_all_products_complete = True
        self.transition_ab.save(update_fields=["requires_all_products_complete"])
        # Заявка ещё не входила в status_a через сервис — лениво создаём прогресс явно,
        # чтобы у продукта появился прогресс на начальном подстатусе (не финальном).
        InteractionProductStatusService.get_or_create_progress(self.instance)

        with self.assertRaises(ProductsNotCompleteError):
            WorkflowService(self.instance).transition(self.status_b.id, self.manager)

    def test_allows_transition_once_all_products_complete(self) -> None:
        """После того, как продукт дошёл до финального подстатуса, переход с requires_all_products_complete проходит."""
        # is_initial=True и is_final=True одновременно — валидный крайний случай: статус с
        # единственным подстатусом, на который продукт сразу входит уже готовым.
        WorkflowStatusFactory(
            template=self.template, parent=self.status_a, order=1, is_initial=True, is_final=True,
        )
        InteractionProductFactory(interaction=self.interaction)
        self.transition_ab.requires_all_products_complete = True
        self.transition_ab.save(update_fields=["requires_all_products_complete"])
        # Заявка ещё не входила в status_a через сервис — лениво создаём прогресс явно, как
        # это сделал бы transition() при реальном входе в статус.
        InteractionProductStatusService.get_or_create_progress(self.instance)

        log = WorkflowService(self.instance).transition(self.status_b.id, self.manager)

        self.assertEqual(log.to_status_id, self.status_b.id)

    def test_creates_product_progress_for_new_status_with_substatuses(self) -> None:
        """После перехода в статус с подстатусами лениво создаётся прогресс активных продуктов."""
        substatus = WorkflowStatusFactory(template=self.template, parent=self.status_b, order=1, is_initial=True)
        product = InteractionProductFactory(interaction=self.interaction)

        WorkflowService(self.instance).transition(self.status_b.id, self.manager)

        self.assertTrue(
            InteractionProductStatus.objects.filter(interaction_product=product, current_status=substatus).exists(),
        )


class WorkflowServiceTransitionProductTestCase(TestCase):
    """Тесты WorkflowService.transition_product."""

    def setUp(self) -> None:
        """Готовит родительский статус с двумя подстатусами, сделку с продуктом на первом подстатусе."""
        self.template = WorkflowTemplateFactory()
        self.parent_status = WorkflowStatusFactory(template=self.template, order=1, is_initial=True)
        self.substatus_a = WorkflowStatusFactory(
            template=self.template, parent=self.parent_status, order=1, is_initial=True,
        )
        self.substatus_b = WorkflowStatusFactory(
            template=self.template, parent=self.parent_status, order=2, is_final=True,
        )
        self.transition_ab = WorkflowTransitionFactory(
            template=self.template, from_status=self.substatus_a, to_status=self.substatus_b,
        )

        self.manager = UserFactory()
        self.university = UniversityFactory()
        ResponsibleAssignmentFactory(university=self.university, manager=self.manager)
        self.interaction = InteractionFactory(university=self.university)
        self.product = InteractionProductFactory(interaction=self.interaction)
        self.instance = WorkflowInstanceFactory(
            interaction=self.interaction, template=self.template, current_status=self.parent_status,
        )

    def test_creates_progress_lazily_and_moves_to_target_substatus(self) -> None:
        """Первый вызов лениво создаёт прогресс продукта и сразу переводит его на целевой подстатус."""
        log = WorkflowService(self.instance).transition_product(self.product.id, self.substatus_b.id, self.manager)

        progress = InteractionProductStatus.objects.get(interaction_product=self.product)
        self.assertEqual(progress.current_status_id, self.substatus_b.id)
        self.assertEqual(log.interaction_product_id, self.product.id)
        self.assertEqual(log.from_status_id, self.substatus_a.id)
        self.assertEqual(log.to_status_id, self.substatus_b.id)

    def test_raises_when_no_such_transition(self) -> None:
        """Переход, не описанный ребром графа между подстатусами, отклоняется."""
        other_substatus = WorkflowStatusFactory(template=self.template, parent=self.parent_status, order=3)

        with self.assertRaises(TransitionNotAllowedError):
            WorkflowService(self.instance).transition_product(self.product.id, other_substatus.id, self.manager)

    def test_raises_permission_denied_for_unassigned_user(self) -> None:
        """Пользователь без доступа к workflow сделки отклоняется — права те же, что и на сделку целиком."""
        with self.assertRaises(PermissionDenied):
            WorkflowService(self.instance).transition_product(self.product.id, self.substatus_b.id, UserFactory())

    def test_raises_when_comment_required_but_missing(self) -> None:
        """requires_comment=True на переходе между подстатусами без комментария отклоняется."""
        self.transition_ab.requires_comment = True
        self.transition_ab.save(update_fields=["requires_comment"])

        with self.assertRaises(CommentRequiredError):
            WorkflowService(self.instance).transition_product(self.product.id, self.substatus_b.id, self.manager, comment="")

    def test_second_transition_uses_existing_progress_as_starting_point(self) -> None:
        """Повторный переход отталкивается от уже созданного прогресса, а не от начального подстатуса заново."""
        WorkflowService(self.instance).transition_product(self.product.id, self.substatus_b.id, self.manager)
        third_substatus = WorkflowStatusFactory(template=self.template, parent=self.parent_status, order=3)
        WorkflowTransitionFactory(template=self.template, from_status=self.substatus_b, to_status=third_substatus)

        log = WorkflowService(self.instance).transition_product(self.product.id, third_substatus.id, self.manager)

        self.assertEqual(log.from_status_id, self.substatus_b.id)


class WorkflowServiceAvailableTransitionsTestCase(TestCase):
    """Тесты WorkflowService.available_transitions."""

    def test_returns_transitions_from_current_status_for_assigned_manager(self) -> None:
        """Назначенному КАМу возвращаются переходы с текущего статуса."""
        template = WorkflowTemplateFactory()
        status_a = WorkflowStatusFactory(template=template, order=1)
        status_b = WorkflowStatusFactory(template=template, order=2)
        transition = WorkflowTransitionFactory(template=template, from_status=status_a, to_status=status_b)

        manager = UserFactory()
        university = UniversityFactory()
        ResponsibleAssignmentFactory(university=university, manager=manager)
        instance = WorkflowInstanceFactory(
            interaction=InteractionFactory(university=university), template=template, current_status=status_a,
        )

        transitions = list(WorkflowService(instance).available_transitions(manager))

        self.assertEqual(transitions, [transition])

    def test_returns_empty_for_unassigned_user(self) -> None:
        """Пользователю без доступа к workflow заявки список переходов не отдаётся."""
        template = WorkflowTemplateFactory()
        status_a = WorkflowStatusFactory(template=template, order=1)
        status_b = WorkflowStatusFactory(template=template, order=2)
        WorkflowTransitionFactory(template=template, from_status=status_a, to_status=status_b)
        instance = WorkflowInstanceFactory(template=template, current_status=status_a)

        transitions = list(WorkflowService(instance).available_transitions(UserFactory()))

        self.assertEqual(transitions, [])


class ProductProgressScopedToParentStatusTestCase(TestCase):
    """
    Финальный ревью-фикс #1: строка прогресса продукта (1:1) должна сбрасываться, а не
    оставаться "залипшей", когда сделка переходит из ОДНОГО статуса с подстатусами
    (A) в ДРУГОЙ статус с подстатусами (B). Это ровно сценарий, который воспроизвёл
    ревьюер: "Внедрение продукта" → ... → "Обучение преподавателей".
    """

    def setUp(self) -> None:
        """Готовит шаблон с двумя статусами A и B, у каждого своя цепочка подстатусов."""
        self.template = WorkflowTemplateFactory()
        self.status_a = WorkflowStatusFactory(template=self.template, order=1, is_initial=True)
        self.status_b = WorkflowStatusFactory(template=self.template, order=2)
        self.a1 = WorkflowStatusFactory(template=self.template, parent=self.status_a, order=1, is_initial=True)
        self.a2 = WorkflowStatusFactory(template=self.template, parent=self.status_a, order=2, is_final=True)
        self.b1 = WorkflowStatusFactory(template=self.template, parent=self.status_b, order=1, is_initial=True)
        self.b2 = WorkflowStatusFactory(template=self.template, parent=self.status_b, order=2, is_final=True)

        WorkflowTransitionFactory(template=self.template, from_status=self.a1, to_status=self.a2)
        WorkflowTransitionFactory(template=self.template, from_status=self.status_a, to_status=self.status_b)
        WorkflowTransitionFactory(template=self.template, from_status=self.b1, to_status=self.b2)

        self.manager = UserFactory()
        self.university = UniversityFactory()
        ResponsibleAssignmentFactory(university=self.university, manager=self.manager)
        self.interaction = InteractionFactory(university=self.university)
        self.product = InteractionProductFactory(interaction=self.interaction)
        self.instance = WorkflowInstanceFactory(
            interaction=self.interaction, template=self.template, current_status=self.status_a,
        )

    def test_stale_progress_reset_and_product_reachable_after_second_parent_status(self) -> None:
        """
        Продукт доходит до финального подстатуса A, сделка переходит A→B — прогресс продукта
        по A не должен ошибочно засчитываться как прогресс по B, и продукт должен снова быть
        доступен для transition_product под B (не залипать на ребре графа статуса A).
        """
        # Продукт проходит цепочку подстатусов A до финального.
        WorkflowService(self.instance).transition_product(self.product.id, self.a2.id, self.manager)
        progress = InteractionProductStatus.objects.get(interaction_product=self.product)
        self.assertEqual(progress.current_status_id, self.a2.id)
        self.assertTrue(InteractionProductStatusService.is_complete(self.instance))

        # Сделка переходит из A в B (обычное ребро, без requires_all_products_complete) —
        # WorkflowService.transition() лениво вызывает get_or_create_progress() на новом статусе.
        WorkflowService(self.instance).transition(self.status_b.id, self.manager)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.current_status_id, self.status_b.id)

        # (a) Прогресс продукта должен быть сброшен на начальный подстатус B, и is_complete()
        # для B должен корректно вернуть False — продукт ещё не начал подстатусы B.
        progress.refresh_from_db()
        self.assertEqual(progress.current_status_id, self.b1.id)
        self.assertFalse(InteractionProductStatusService.is_complete(self.instance))

        # (b) Продукт должен быть снова достижим через transition_product под B (b1 -> b2),
        # а не "мертво" застрять из-за ребра графа, которое существовало только для A.
        log = WorkflowService(self.instance).transition_product(self.product.id, self.b2.id, self.manager)
        self.assertEqual(log.from_status_id, self.b1.id)
        self.assertEqual(log.to_status_id, self.b2.id)
        progress.refresh_from_db()
        self.assertEqual(progress.current_status_id, self.b2.id)
        self.assertTrue(InteractionProductStatusService.is_complete(self.instance))

    def test_get_or_create_progress_resets_stale_row_without_creating_second_row(self) -> None:
        """get_or_create_progress под B сбрасывает существующую (1:1) строку, а не создаёт новую."""
        WorkflowService(self.instance).transition_product(self.product.id, self.a2.id, self.manager)
        self.assertEqual(InteractionProductStatus.objects.filter(interaction_product=self.product).count(), 1)

        WorkflowService(self.instance).transition(self.status_b.id, self.manager)
        self.instance.refresh_from_db()

        progress_rows = InteractionProductStatusService.get_or_create_progress(self.instance)
        self.assertEqual(InteractionProductStatus.objects.filter(interaction_product=self.product).count(), 1)
        self.assertEqual(len(progress_rows), 1)
        self.assertEqual(progress_rows[0].current_status_id, self.b1.id)


class CrossLevelTransitionGuardTestCase(TestCase):
    """
    Финальный ревью-фикс #3: даже если бы ребро графа, пересекающее уровни (сделка <-> подстатус
    продукта), как-то оказалось в БД в обход WorkflowTransition.clean(), сервисный слой должен
    сам отклонить его — defense-in-depth независимо от валидации на уровне модели/API.
    """

    def setUp(self) -> None:
        """Готовит статус с подстатусом и сделку на этом статусе."""
        self.template = WorkflowTemplateFactory()
        self.status_a = WorkflowStatusFactory(template=self.template, order=1, is_initial=True)
        self.status_b = WorkflowStatusFactory(template=self.template, order=2)
        self.substatus_a1 = WorkflowStatusFactory(
            template=self.template, parent=self.status_a, order=1, is_initial=True,
        )

        self.manager = UserFactory()
        self.university = UniversityFactory()
        ResponsibleAssignmentFactory(university=self.university, manager=self.manager)
        self.interaction = InteractionFactory(university=self.university)
        self.product = InteractionProductFactory(interaction=self.interaction)
        self.instance = WorkflowInstanceFactory(
            interaction=self.interaction, template=self.template, current_status=self.status_a,
        )

    def test_transition_rejects_edge_landing_on_substatus(self) -> None:
        """transition() отклоняет ребро status_a -> substatus_a1, даже если оно существует в БД."""
        WorkflowTransition.objects.create(
            template=self.template, from_status=self.status_a, to_status=self.substatus_a1,
        )

        with self.assertRaises(TransitionNotAllowedError):
            WorkflowService(self.instance).transition(self.substatus_a1.id, self.manager)

    def test_transition_product_rejects_edge_landing_outside_current_parent(self) -> None:
        """transition_product() отклоняет ребро substatus_a1 -> status_b (статус верхнего уровня), даже если оно существует в БД."""
        WorkflowTransition.objects.create(
            template=self.template, from_status=self.substatus_a1, to_status=self.status_b,
        )

        with self.assertRaises(TransitionNotAllowedError):
            WorkflowService(self.instance).transition_product(self.product.id, self.status_b.id, self.manager)
