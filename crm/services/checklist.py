from django.utils import timezone

from crm.models import InstanceChecklistProgress, WorkflowInstance


class ChecklistService:
    """Прогресс по чек-листу текущего статуса заявки."""

    @staticmethod
    def get_or_create_progress(instance: WorkflowInstance) -> list[InstanceChecklistProgress]:
        """
        Строки прогресса для активных пунктов чек-листа текущего статуса заявки.

        Создаются лениво — только когда заявка реально входит в статус, а не
        заранее на все статусы шаблона при создании WorkflowInstance.
        """
        items = instance.current_status.checklist_items.filter(is_active=True)
        existing_item_ids = set(instance.checklist_progress.values_list("checklist_item_id", flat=True))

        created = [
            InstanceChecklistProgress(instance=instance, checklist_item=item)
            for item in items
            if item.id not in existing_item_ids
        ]
        if created:
            InstanceChecklistProgress.objects.bulk_create(created)

        return list(instance.checklist_progress.filter(checklist_item__in=items).select_related("checklist_item"))

    @staticmethod
    def toggle(instance: WorkflowInstance, checklist_item_id: int, user, is_done: bool) -> InstanceChecklistProgress:
        """Отмечает/снимает отметку выполнения пункта чек-листа для заявки."""
        progress, _ = InstanceChecklistProgress.objects.get_or_create(
            instance=instance, checklist_item_id=checklist_item_id,
        )
        progress.is_done = is_done
        progress.done_at = timezone.now() if is_done else None
        progress.done_by = user if is_done else None
        progress.save(update_fields=["is_done", "done_at", "done_by"])
        return progress

    @staticmethod
    def is_complete(instance: WorkflowInstance) -> bool:
        """True, если все активные пункты чек-листа текущего статуса отмечены выполненными."""
        required_ids = set(instance.current_status.checklist_items.filter(is_active=True).values_list("id", flat=True))
        if not required_ids:
            return True

        done_ids = set(
            instance.checklist_progress.filter(
                is_done=True, checklist_item_id__in=required_ids,
            ).values_list("checklist_item_id", flat=True),
        )
        return required_ids <= done_ids
