from django.core.exceptions import ValidationError
from django.test import TestCase

from sova.crm.tests.factories import WorkflowStatusFactory, WorkflowTemplateFactory, WorkflowTransitionFactory


class WorkflowTransitionCleanTestCase(TestCase):
    """Тесты WorkflowTransition.clean()."""

    def test_rejects_edge_from_top_level_status_to_substatus(self) -> None:
        """Ребро графа не может вести из статуса верхнего уровня прямо в подстатус."""
        template = WorkflowTemplateFactory()
        top_level = WorkflowStatusFactory(template=template, order=1)
        other_top_level = WorkflowStatusFactory(template=template, order=2)
        substatus = WorkflowStatusFactory(template=template, parent=other_top_level, order=1)
        transition = WorkflowTransitionFactory.build(template=template, from_status=top_level, to_status=substatus)

        with self.assertRaises(ValidationError):
            transition.full_clean()

    def test_rejects_edge_between_substatuses_of_different_parents(self) -> None:
        """Ребро графа не может вести между подстатусами разных родительских статусов."""
        template = WorkflowTemplateFactory()
        parent_a = WorkflowStatusFactory(template=template, order=1)
        parent_b = WorkflowStatusFactory(template=template, order=2)
        sub_a = WorkflowStatusFactory(template=template, parent=parent_a, order=1)
        sub_b = WorkflowStatusFactory(template=template, parent=parent_b, order=1)
        transition = WorkflowTransitionFactory.build(template=template, from_status=sub_a, to_status=sub_b)

        with self.assertRaises(ValidationError):
            transition.full_clean()

    def test_allows_edge_between_substatuses_of_same_parent(self) -> None:
        """Ребро графа между подстатусами одного родителя допустимо (не задевает новую проверку)."""
        template = WorkflowTemplateFactory()
        parent = WorkflowStatusFactory(template=template, order=1)
        sub_1 = WorkflowStatusFactory(template=template, parent=parent, order=1, is_initial=True)
        sub_2 = WorkflowStatusFactory(template=template, parent=parent, order=2, is_final=True)
        transition = WorkflowTransitionFactory.build(template=template, from_status=sub_1, to_status=sub_2)

        transition.full_clean()
