from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from sova.interactions.exceptions import NoActiveResponsibleError
from sova.interactions.models import Interaction, Responsible


class ResponsibleService:
    """
    Назначение и снятие ответственного менеджера (КАМ) на взаимодействие.

    Responsible — журнал с историей: запись никогда не перезаписывается, смена
    ответственного закрывает действующую запись (`unassigned_at`) и создаёт новую.
    Одна действующая запись на взаимодействие гарантируется ограничением БД
    `one_active_responsible_per_interaction`; блокировка строки взаимодействия
    сериализует параллельные назначения, чтобы вместо ошибки ограничения второй
    запрос дождался первого.
    """

    @transaction.atomic
    def assign(
        self,
        interaction: Interaction,
        manager: AbstractBaseUser,
        assigned_by: AbstractBaseUser | None,
    ) -> tuple[Responsible, bool]:
        """
        Назначает менеджера ответственным за взаимодействие.

        Возвращает пару (запись, создана_ли_новая). Если менеджер уже
        ответственный, история не меняется и возвращается действующая запись.
        """
        Interaction.objects.select_for_update().get(pk=interaction.pk)
        current = self._get_current(interaction=interaction)

        if current is not None and current.manager_id == manager.pk:
            return current, False
        if current is not None:
            self._close(responsible=current)

        responsible = Responsible.objects.create(
            interaction=interaction,
            manager=manager,
            assigned_by=assigned_by,
        )
        return responsible, True

    @transaction.atomic
    def unassign(self, interaction: Interaction) -> Responsible:
        """Снимает действующего ответственного, не назначая нового."""
        Interaction.objects.select_for_update().get(pk=interaction.pk)
        current = self._get_current(interaction=interaction)
        if current is None:
            raise NoActiveResponsibleError
        self._close(responsible=current)
        return current

    def _get_current(self, interaction: Interaction) -> Responsible | None:
        """Возвращает действующее назначение взаимодействия."""
        return Responsible.objects.filter(
            interaction=interaction,
            unassigned_at__isnull=True,
        ).first()

    def _close(self, responsible: Responsible) -> None:
        """Закрывает назначение текущим моментом."""
        responsible.unassigned_at = timezone.now()
        responsible.save(update_fields=["unassigned_at"])


responsible_service = ResponsibleService()
