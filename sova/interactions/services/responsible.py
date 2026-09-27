from collections.abc import Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from accounts.models import SystemRole
from accounts.policy import effective_role
from accounts.services import account_service
from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError, NoActiveResponsibleError
from sova.interactions.models import Contract, Interaction, Responsible
from sova.notifications.enum import NotifyType
from sova.notifications.services.event_notification import event_notification_service
from sova.notifications.services.links import interaction_link
from sova.notifications.services.message import Message
from sova.processes.enum import ActionInstanceStatus
from sova.processes.models import ActionInstance


class ResponsibleService:
    """
    Назначение и снятие ответственных менеджеров (КАМов) взаимодействия.

    Responsible — журнал с историей: запись никогда не перезаписывается, снятие закрывает
    её (`unassigned_at`). Действующих КАМов у взаимодействия может быть несколько; один
    менеджер не назначается на взаимодействие дважды — это гарантирует ограничение БД
    `one_active_responsible_per_manager`, а блокировка строки взаимодействия сериализует
    параллельные назначения, чтобы вместо ошибки ограничения второй запрос дождался первого.
    Назначение действия процесса не трогает: новые исполнения создаются без ответственного
    (пул КАМов взаимодействия). При снятии открытые действия снятого менеджера уходят в пул,
    завершённые исполнения остаются в истории. Новый КАМ получает уведомление «Назначение КАМа»
    по настройкам этого типа.

    Права (кого можно назначить и снять) проверяются снаружи — `responsible_policy`; `assign` / `unassign` —
    низкоуровневые, ими пользуются и служебные пути (демо-данные, импорт).

    Менеджеров из реестра договоров назначает импорт: они становятся ответственными договора
    (`sync_contract_responsibles`) и на взаимодействие сами не переходят — это подсказка для назначения.
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
    def assign_by(
        self,
        interaction: Interaction,
        manager: AbstractBaseUser,
        actor: AbstractBaseUser,
    ) -> tuple[Responsible, bool]:
        """
        Назначение от имени пользователя: руководитель, назначающий свободного КАМа, забирает его в команду.

        Права (кого можно назначить) проверяет вызывающий через `assignable_managers`. Если КАМа забрал другой
        руководитель после проверки, `KamHasHeadError` откатывает и назначение.
        """
        if effective_role(actor) == SystemRole.HEAD and manager.pk != actor.pk:
            account_service.claim(kam=manager, head=actor, actor=actor)
        return self.assign(interaction=interaction, manager=manager, assigned_by=actor)

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

    @transaction.atomic
    def unassign_everywhere(self, manager: AbstractBaseUser) -> list[Responsible]:
        """
        Снимает менеджера со всех взаимодействий и договоров реестра — при деактивации учётной записи.

        Каждое снятие со взаимодействия — как `unassign`: запись закрывается, открытые задачи менеджера уходят в пул.
        Взаимодействие, где он был единственным КАМом, становится ничьим и видно всем ролям. Назначения из реестра
        на договоры (без взаимодействия) просто закрываются: задач у них нет.
        """
        current = Responsible.objects.filter(manager=manager, unassigned_at__isnull=True)
        released = list(current.select_for_update().filter(interaction__isnull=True))
        for responsible in released:
            self._close(responsible=responsible)
        on_interactions = current.select_related("interaction").filter(interaction__isnull=False)
        return released + [
            self.unassign(interaction=responsible.interaction, manager=manager) for responsible in on_interactions
        ]

    @transaction.atomic
    def sync_contract_responsibles(
        self,
        contract: Contract,
        managers: Iterable[AbstractBaseUser],
        assigned_by: AbstractBaseUser | None,
    ) -> None:
        """
        Приводит действующих ответственных headless-договора к `managers` (реестр — источник правды).

        Недостающие назначаются от имени `assigned_by`, отсутствующие в `managers` снимаются и остаются в
        истории. Уведомлений нет: у headless-договора нет карточки, на которую вела бы ссылка.
        """
        wanted = {manager.pk: manager for manager in managers}
        current = Responsible.objects.select_for_update().filter(
            contract=contract,
            interaction__isnull=True,
            unassigned_at__isnull=True,
        )
        kept: set[int] = set()
        for responsible in current:
            if responsible.manager_id in wanted:
                kept.add(responsible.manager_id)
            else:
                self._close(responsible=responsible)
        for manager_id, manager in wanted.items():
            if manager_id not in kept:
                Responsible.objects.create(contract=contract, manager=manager, assigned_by=assigned_by)

    def _get_active(self, interaction: Interaction, manager_id: int) -> Responsible | None:
        """Возвращает действующее назначение менеджера на взаимодействие."""
        return Responsible.objects.filter(
            interaction=interaction,
            manager_id=manager_id,
            unassigned_at__isnull=True,
        ).first()

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
        text = (
            f"{manager.get_full_name()}({manager.email}), Вас назначили КАМом — "
            f"{interaction.university or interaction.b2c_client}"
        )
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
