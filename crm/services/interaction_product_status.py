from django.utils import timezone

from crm.models import InteractionProductStatus, WorkflowInstance


class InteractionProductStatusService:
    """Прогресс продуктов сделки по подстатусам текущего статуса заявки."""

    @staticmethod
    def get_or_create_progress(instance: WorkflowInstance) -> list[InteractionProductStatus]:
        """
        Строки прогресса для активных продуктов сделки, когда текущий статус заявки имеет подстатусы.

        Создаются лениво — только когда заявка реально входит в статус с подстатусами,
        не заранее на все продукты при добавлении InteractionProduct.

        InteractionProductStatus — 1:1 с продуктом на всё время его жизни, а не одна строка
        на пару (продукт, родительский статус). Поэтому если у продукта уже есть строка, но
        она осталась от ДРУГОГО родительского статуса (сделка проходила через него раньше,
        затем вернулась/перешла в новый статус с подстатусами), эта строка не создаётся
        заново, а сбрасывается на начальный подстатус текущего родительского статуса — полная
        история движения продукта не теряется, она остаётся в TransitionLog.
        """
        initial_substatus = instance.current_status.substatuses.filter(is_initial=True).first()
        if initial_substatus is None:
            return []

        products = instance.interaction.products.filter(is_active=True)
        existing_by_product_id = {
            progress.interaction_product_id: progress
            for progress in InteractionProductStatus.objects.filter(
                interaction_product__in=products,
            ).select_related("current_status")
        }

        now = timezone.now()
        created = []
        reset = []
        for product in products:
            existing_progress = existing_by_product_id.get(product.id)
            if existing_progress is None:
                created.append(
                    InteractionProductStatus(
                        interaction_product=product,
                        current_status=initial_substatus,
                        status_changed_at=now,
                    ),
                )
            elif existing_progress.current_status.parent_id != instance.current_status_id:
                existing_progress.current_status = initial_substatus
                existing_progress.status_changed_at = now
                reset.append(existing_progress)

        if created:
            InteractionProductStatus.objects.bulk_create(created)
        if reset:
            InteractionProductStatus.objects.bulk_update(reset, ["current_status", "status_changed_at"])

        return list(
            InteractionProductStatus.objects.filter(
                interaction_product__in=products,
            ).select_related("interaction_product", "current_status"),
        )

    @staticmethod
    def is_complete(instance: WorkflowInstance) -> bool:
        """True, если у текущего статуса заявки нет подстатусов либо все активные продукты завершили их."""
        if not instance.current_status.substatuses.exists():
            return True

        products = instance.interaction.products.filter(is_active=True)
        if not products.exists():
            return True

        # Скоуп по current_status__parent=instance.current_status обязателен: строка прогресса
        # 1:1 с продуктом и может остаться от ПРЕДЫДУЩЕГО родительского статуса (см.
        # get_or_create_progress) — без этого фильтра она ошибочно засчиталась бы как прогресс
        # по текущему статусу.
        progress = list(
            InteractionProductStatus.objects.filter(
                interaction_product__in=products,
                current_status__parent=instance.current_status,
            ).select_related("current_status"),
        )
        if len(progress) < products.count():
            return False

        return all(p.current_status.is_final for p in progress)
