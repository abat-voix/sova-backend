from django.db import transaction as db_transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from sova.crm.models import InteractionProduct, InteractionProductStatus, TransitionLog, WorkflowInstance, WorkflowTransition
from sova.crm.services import ChecklistService
from sova.crm.services import InteractionProductStatusService


class TransitionNotAllowedError(ValidationError):
    """Перехода с текущего статуса на запрошенный не существует в этом workflow."""


class ChecklistNotCompleteError(ValidationError):
    """Не все обязательные пункты чек-листа текущего статуса отмечены."""


class ProductsNotCompleteError(ValidationError):
    """Не все активные продукты сделки завершили прохождение подстатусов текущего статуса."""


class CommentRequiredError(ValidationError):
    """Переход требует комментарий, а он не передан."""


class WorkflowService:
    """
    Выполнение перехода по workflow конкретной заявки.

    Единственная точка, где реально применяются WorkflowTransition.required_permission,
    requires_comment, requires_checklist_complete и requires_all_products_complete — до сих
    пор эти поля были только данными без потребителя, т.к. не было эндпоинта "выполнить переход".
    """

    def __init__(self, instance: WorkflowInstance):
        self.instance = instance

    def available_transitions(self, user) -> QuerySet[WorkflowTransition]:
        """Переходы, структурно доступные с текущего статуса и разрешённые этому пользователю."""
        queryset = WorkflowTransition.objects.filter(
            template=self.instance.template,
            from_status=self.instance.current_status,
        ).select_related("to_status")

        if not user.has_perm("workflow.transition", self.instance):
            return queryset.none()

        return queryset

    def transition(self, to_status_id: int, user, comment: str = "") -> TransitionLog:
        """
        Выполняет переход на to_status_id, если это разрешено и заявка готова.

        Порядок проверок: существование ребра графа → право на workflow этой заявки
        (django-rules, is_assigned_manager | can_transition_backward) → доп. право
        конкретного перехода (required_permission) → обязательность комментария →
        завершённость чек-листа текущего статуса → завершённость подстатусов у всех
        активных продуктов сделки (если у текущего статуса они есть).
        """
        with db_transaction.atomic():
            locked_instance = WorkflowInstance.objects.select_for_update().get(pk=self.instance.pk)

            transition = WorkflowTransition.objects.filter(
                template=locked_instance.template,
                from_status=locked_instance.current_status,
                to_status_id=to_status_id,
            ).select_related("to_status").first()
            if transition is None:
                raise TransitionNotAllowedError("Такой переход не существует в этом workflow.")
            if transition.to_status.parent_id is not None:
                raise TransitionNotAllowedError(
                    "Переход сделки должен вести на статус верхнего уровня, а не на подстатус продукта.",
                )

            if not user.has_perm("workflow.transition", locked_instance):
                raise PermissionDenied("Нет доступа к workflow этой заявки.")
            if transition.required_permission and not user.has_perm(transition.required_permission):
                raise PermissionDenied(f"Недостаточно прав для перехода: требуется {transition.required_permission}.")
            if transition.requires_comment and not comment:
                raise CommentRequiredError("Этот переход требует комментарий.")
            if transition.requires_checklist_complete and not ChecklistService.is_complete(locked_instance):
                raise ChecklistNotCompleteError("Не все пункты чек-листа текущего статуса отмечены.")
            if transition.requires_all_products_complete and not InteractionProductStatusService.is_complete(locked_instance):
                raise ProductsNotCompleteError("Не все продукты сделки завершили внедрение по подстатусам.")

            log = TransitionLog.objects.create(
                instance=locked_instance,
                from_status=locked_instance.current_status,
                to_status=transition.to_status,
                user=user,
                comment=comment,
            )

            locked_instance.current_status = transition.to_status
            locked_instance.status_changed_at = timezone.now()
            locked_instance.save(update_fields=["current_status", "status_changed_at"])

            # Прогресс чек-листа и прогресс продуктов по подстатусам нового статуса создаём
            # сразу, чтобы фронт увидел их в том же ответе, не дожидаясь отдельного запроса.
            ChecklistService.get_or_create_progress(locked_instance)
            InteractionProductStatusService.get_or_create_progress(locked_instance)

        # TODO: уведомление о переходе (Telegram/почта — см. Q&A постановщика про
        # уведомления по зависшим заявкам) — в проекте пока нет Celery/очереди задач,
        # подключается здесь через .delay(...) когда появится.

        return log

    def transition_product(
        self, interaction_product_id: int, to_status_id: int, user, comment: str = "",
    ) -> TransitionLog:
        """
        Выполняет переход продукта сделки по подстатусам текущего статуса заявки.

        Права и требования (permission/comment) проверяются так же, как в transition() —
        отдельных прав на уровне продукта в системе нет, право выдаётся на workflow сделки
        целиком. Если у продукта ещё нет строки прогресса, она создаётся лениво на
        начальном подстатусе текущего статуса заявки — тем самым transition_product можно
        вызывать сразу после того, как сделка вошла в статус с подстатусами, не дожидаясь
        отдельного вызова get_or_create_progress.
        """
        with db_transaction.atomic():
            locked_instance = WorkflowInstance.objects.select_for_update().get(pk=self.instance.pk)
            product = InteractionProduct.objects.filter(
                pk=interaction_product_id, interaction_id=locked_instance.interaction_id, is_active=True,
            ).first()
            if product is None:
                raise TransitionNotAllowedError("Продукт не найден в этой сделке или деактивирован.")

            # select_for_update() здесь не блокирует ещё не существующую строку — это безопасно
            # только потому, что конкурентные вызовы для этой же сделки уже сериализованы
            # блокировкой WorkflowInstance выше, а InteractionProductStatus.interaction_product
            # — OneToOneField (БД не даст создать вторую строку). Если когда-нибудь появится
            # путь создания строки прогресса продукта БЕЗ внешней блокировки instance, гонка
            # не пройдёт тихо: bulk_create в InteractionProductStatusService.get_or_create_progress
            # не использует ignore_conflicts=True, так что упадёт с IntegrityError, а не молча
            # проигнорирует дубликат.
            progress = InteractionProductStatus.objects.select_for_update().filter(
                interaction_product=product,
            ).select_related("current_status").first()
            if progress is None:
                initial_substatus = locked_instance.current_status.substatuses.filter(is_initial=True).first()
                if initial_substatus is None:
                    raise TransitionNotAllowedError("Текущий статус заявки не подразумевает подстатусов продукта.")
                progress = InteractionProductStatus.objects.create(
                    interaction_product=product, current_status=initial_substatus, status_changed_at=timezone.now(),
                )
            elif progress.current_status.parent_id != locked_instance.current_status_id:
                # Строка прогресса осталась от предыдущего родительского статуса сделки (см.
                # InteractionProductStatusService.get_or_create_progress) — сбрасываем её на
                # начальный подстатус текущего статуса вместо создания второй строки (1:1).
                initial_substatus = locked_instance.current_status.substatuses.filter(is_initial=True).first()
                if initial_substatus is None:
                    raise TransitionNotAllowedError("Текущий статус заявки не подразумевает подстатусов продукта.")
                progress.current_status = initial_substatus
                progress.status_changed_at = timezone.now()
                progress.save(update_fields=["current_status", "status_changed_at"])

            transition = WorkflowTransition.objects.filter(
                template=locked_instance.template,
                from_status=progress.current_status,
                to_status_id=to_status_id,
            ).select_related("to_status").first()
            if transition is None:
                raise TransitionNotAllowedError("Такой переход не существует в этом workflow.")
            if transition.to_status.parent_id != locked_instance.current_status_id:
                raise TransitionNotAllowedError(
                    "Переход продукта должен вести на подстатус текущего статуса сделки.",
                )

            if not user.has_perm("workflow.transition", locked_instance):
                raise PermissionDenied("Нет доступа к workflow этой заявки.")
            if transition.required_permission and not user.has_perm(transition.required_permission):
                raise PermissionDenied(f"Недостаточно прав для перехода: требуется {transition.required_permission}.")
            if transition.requires_comment and not comment:
                raise CommentRequiredError("Этот переход требует комментарий.")

            log = TransitionLog.objects.create(
                instance=locked_instance,
                interaction_product=product,
                from_status=progress.current_status,
                to_status=transition.to_status,
                user=user,
                comment=comment,
            )

            progress.current_status = transition.to_status
            progress.status_changed_at = timezone.now()
            progress.save(update_fields=["current_status", "status_changed_at"])

        return log
