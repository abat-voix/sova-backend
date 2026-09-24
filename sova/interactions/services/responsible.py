from collections.abc import Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError, NoActiveResponsibleError
from sova.interactions.models import Interaction, Responsible
from sova.notifications.enum import NotifyType
from sova.notifications.services.event_notification import event_notification_service
from sova.notifications.services.links import interaction_link
from sova.notifications.services.message import Message
from sova.processes.enum import ActionInstanceStatus
from sova.processes.models import ActionInstance


class ResponsibleService:
    """
    Назначение и снятие ответственных менеджеров (КАМов) взаимодействия.

    Responsible — журнал с историей: запись никогда не перезаписывается, смена
    ответственного закрывает действующую запись (`unassigned_at`) и создаёт новую.
    Одна действующая запись на взаимодействие гарантируется ограничением БД
    `one_active_responsible_per_interaction`; блокировка строки взаимодействия
    сериализует параллельные назначения, чтобы вместо ошибки ограничения второй
    запрос дождался первого.

    Менеджер из реестра договоров (ФИО строкой) не назначается автоматически: по ФИО подбирается
    пользователь-подсказка (`suggest_manager`), а назначение делает человек явно.
    Responsible — журнал с историей: запись никогда не перезаписывается, снятие закрывает
    её (`unassigned_at`). Действующих КАМов у взаимодействия может быть несколько; один
    менеджер не назначается на взаимодействие дважды — это гарантирует ограничение БД
    `one_active_responsible_per_manager`, а блокировка строки взаимодействия сериализует
    параллельные назначения, чтобы вместо ошибки ограничения второй запрос дождался первого.
    Назначение действия процесса не трогает: новые исполнения создаются без ответственного
    (пул КАМов взаимодействия). При снятии открытые действия снятого менеджера уходят в пул,
    завершённые исполнения остаются в истории. Новый КАМ получает уведомление «Назначение КАМа»
    по настройкам этого типа.
    """

    @transaction.atomic
    def assign(
        self,
        interaction: Interaction,
        manager: AbstractBaseUser,
        assigned_by: AbstractBaseUser | None,
    ) -> tuple[Responsible, bool]:
        """
        Добавляет менеджера к действующим ответственным взаимодействия.

        Возвращает пару (запись, создана_ли_новая). Если менеджер уже
        ответственный, история не меняется и возвращается действующая запись.
        """
        Interaction.objects.select_for_update().get(pk=interaction.pk)
        current = self._get_active(interaction=interaction, manager_id=manager.pk)
        if current is not None:
            return current, False

        responsible = Responsible.objects.create(
            interaction=interaction,
            manager=manager,
            assigned_by=assigned_by,
        )
        self._notify_assigned(interaction=interaction, manager=manager, assigned_by=assigned_by)
        return responsible, True

    @transaction.atomic
    def unassign(self, interaction: Interaction, manager: AbstractBaseUser) -> Responsible:
        """Снимает менеджера с взаимодействия; его открытые действия уходят в пул."""
        Interaction.objects.select_for_update().get(pk=interaction.pk)
        current = self._get_active(interaction=interaction, manager_id=manager.pk)
        if current is None:
            raise NoActiveResponsibleError
        self._close(responsible=current)
        self._release_open_action_instances(interaction=interaction, manager_id=current.manager_id)
        return current

    def _get_active(self, interaction: Interaction, manager_id: int) -> Responsible | None:
        """Возвращает действующее назначение менеджера на взаимодействие."""
    def find_manager(self, full_name: str, users: Iterable[AbstractBaseUser] | None = None) -> AbstractBaseUser:
        """
        Активный пользователь по ФИО из файла: сравнение с first_name/last_name в обоих порядках слов.

        ФИО в файле обычно пишут «Фамилия Имя», а `User.get_full_name()` в Django — «Имя Фамилия».
        Точное сравнение с `get_full_name()` не сработало бы почти никогда — сравниваем с обоими
        порядками, без учёта регистра и лишних пробелов. Отчества в `User` нет, поэтому ФИО с
        отчеством в файле не найдётся. Не найден — `ManagerNotFoundError`, несколько — `AmbiguousManagerError`.
        `users` — уже выбранные активные пользователи, чтобы не запрашивать их на каждое ФИО (списки).
        """
        if users is None:
            users = get_user_model().objects.filter(is_active=True)
        normalized = self._normalize(full_name)
        candidates = [user for user in users if normalized in self._name_variants(user)]
        if not candidates:
            raise ManagerNotFoundError(f"Менеджер не найден: {full_name}")
        if len(candidates) > 1:
            raise AmbiguousManagerError(f"Менеджер неоднозначен: {full_name}")
        return candidates[0]

    def suggest_manager(
        self, full_name: str, users: Iterable[AbstractBaseUser] | None = None
    ) -> AbstractBaseUser | None:
        """Подсказка ответственного по ФИО из файла: единственный найденный пользователь, иначе None."""
        if not full_name:
            return None
        try:
            return self.find_manager(full_name=full_name, users=users)
        except (ManagerNotFoundError, AmbiguousManagerError):
            return None

    def _get_current(self, interaction: Interaction) -> Responsible | None:
        """Возвращает действующее назначение взаимодействия."""
        return Responsible.objects.filter(
            interaction=interaction,
            manager_id=manager_id,
            unassigned_at__isnull=True,
        ).first()

    def _close(self, responsible: Responsible) -> None:
        """Закрывает назначение текущим моментом."""
        responsible.unassigned_at = timezone.now()
        responsible.save(update_fields=["unassigned_at"])

    def _notify_assigned(
        self,
        interaction: Interaction,
        manager: AbstractBaseUser,
        assigned_by: AbstractBaseUser | None,
    ) -> None:
        """Уведомляет нового КАМа; назначившему самого себя не отправляется — его отсекает actor."""
        text = f"Вас назначили КАМом — {interaction.university or interaction.b2c_client}"
        event_notification_service.notify(
            notify_type=NotifyType.KAM_ASSIGNED,
            message=Message(text=text, link=interaction_link(interaction_id=interaction.pk)),
            responsible=manager,
            head=assigned_by,
            actor=assigned_by,
        )

    def _release_open_action_instances(self, interaction: Interaction, manager_id: int) -> int:
        """
        Возвращает в пул открытые задачи снятого менеджера; завершённые исполнения остаются в истории.

        Новые исполнения создаются без ответственного, так что это касается задач, которые получили
        ответственного до перехода на несколько КАМов.
        """
        return ActionInstance.objects.filter(
            stage_instance__workflow_instance__interaction=interaction,
            status__in=(ActionInstanceStatus.PENDING, ActionInstanceStatus.IN_PROGRESS),
            responsible_id=manager_id,
        ).update(responsible=None)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).casefold()

    @classmethod
    def _name_variants(cls, user: AbstractBaseUser) -> set[str]:
        first, last = user.first_name, user.last_name
        return {cls._normalize(f"{first} {last}"), cls._normalize(f"{last} {first}")}


responsible_service = ResponsibleService()
