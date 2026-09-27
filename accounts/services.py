from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.db.models import Q, QuerySet

from accounts.exceptions import KamHasHeadError, NotInTeamError
from accounts.models import Supervision, SystemRole, UserRole
from sova.notifications.enum import NotifyType
from sova.notifications.services.event_notification import event_notification_service
from sova.notifications.services.message import Message


def get_system_role(user) -> str | None:
    """Возвращает прикладную роль пользователя в СОВА или None, если роли нет."""
    # У обратной связи OneToOne отсутствие записи выглядит как AttributeError
    assignment = getattr(user, "system_role", None)
    return assignment.role if assignment else None


def visible_users(user) -> QuerySet:
    """
    Пользователи, которых видит `user` согласно своей роли в СОВА.

    Руководитель видит активных КАМов своей команды и свободных (без руководителя). Администратор платформы видит
    всех, включая администраторов и неактивных: ими он управляет (роль, руководитель, активность); список по
    умолчанию отбирает активных сам `UserViewSet`.
    Остальным роль списка не даёт: запрос к API отклоняется разрешением `CanListUsers`, а сам набор пуст.
    """
    user_model = get_user_model()
    role = SystemRole.PLATFORM_ADMIN if user.is_superuser else get_system_role(user)

    if role == SystemRole.PLATFORM_ADMIN:
        return user_model.objects.all()
    if role == SystemRole.HEAD:
        return user_model.objects.filter(
            Q(supervision__head=user) | Q(supervision__isnull=True),
            system_role__role=SystemRole.KAM,
            is_active=True,
        )
    return user_model.objects.none()


class AccountService:
    """
    Смена роли, активности и руководителя пользователя — единственный путь, которым их меняют API и Django Admin.

    Связь «руководитель — КАМ» (`Supervision`) имеет смысл, только пока оба участника активны и в своих ролях, поэтому
    смена роли и деактивация удаляют все связи пользователя: КАМ теряет руководителя, руководитель — команду.
    Участники удалённых и новых связей получают уведомления «Снятие руководителя» / «Назначение руководителя» по
    настройкам этих типов; инициатор (`actor`) их не получает. Методы, удаляющие связи руководителя, возвращают КАМов,
    оставшихся без руководителя, — вызывающий показывает их инициатору, чтобы тот переназначил команду.
    Руководитель ведёт свою команду сам через `claim`/`release`; перехват чужого КАМа запрещён.
    """

    @transaction.atomic
    def change_role(
        self,
        user: AbstractBaseUser,
        role: str | None,
        actor: AbstractBaseUser | None,
    ) -> list[AbstractBaseUser]:
        """Назначает, меняет или снимает (`role=None`) роль; при настоящей смене роли удаляет связи пользователя."""
        # Роль из БД, а не из кеша `user.system_role`: формы админки кладут туда уже изменённый в памяти `UserRole`
        if UserRole.objects.filter(user=user).values_list("role", flat=True).first() == role:
            return []

        orphans = self._detach(user=user, actor=actor)
        if role is None:
            UserRole.objects.filter(user=user).delete()
        else:
            UserRole.objects.update_or_create(user=user, defaults={"role": role})
        # Сбрасывает закешированную обратную связь `system_role`
        user.refresh_from_db()
        return orphans

    @transaction.atomic
    def deactivate(self, user: AbstractBaseUser, actor: AbstractBaseUser | None) -> list[AbstractBaseUser]:
        """
        Деактивирует пользователя: удаляет его связи и снимает со всех взаимодействий; неактивного не трогает.

        Открытые задачи снятого уходят в пул взаимодействия; взаимодействие, где он был единственным ответственным,
        становится ничьим.
        """
        if not user.is_active:
            return []

        # Импорт внутри метода: сервис ответственных сам зависит от `account_service`
        from sova.interactions.services import responsible_service

        # Сначала деактивация: неактивный пользователь уже не получает уведомлений о своих связях
        user.is_active = False
        user.save(update_fields=["is_active"])
        responsible_service.unassign_everywhere(manager=user)
        return self._detach(user=user, actor=actor)

    def activate(self, user: AbstractBaseUser, actor: AbstractBaseUser | None) -> None:
        """Активирует пользователя; удалённые при деактивации связи не восстанавливаются."""
        if user.is_active:
            return
        user.is_active = True
        user.save(update_fields=["is_active"])

    @transaction.atomic
    def set_supervisor(
        self,
        kam: AbstractBaseUser,
        head: AbstractBaseUser,
        actor: AbstractBaseUser | None,
    ) -> Supervision:
        """
        Назначает КАМу руководителя; прежний руководитель, если был, снимается.

        Тот же руководитель — ничего не меняется и уведомлений нет. Недопустимые роли или неактивные участники —
        `ValidationError` из `Supervision.clean`.
        """
        kam = self._lock_kam(kam)
        supervision = Supervision.objects.select_related("head").filter(kam=kam).first()
        if supervision is not None and supervision.head_id == head.pk:
            return supervision

        previous_head = supervision.head if supervision is not None else None
        supervision = supervision or Supervision(kam=kam)
        supervision.head = head
        supervision.full_clean()
        supervision.save()

        if previous_head is not None:
            self._notify(notify_type=NotifyType.HEAD_UNASSIGNED, kam=kam, head=previous_head, actor=actor, to_kam=False)
        self._notify(notify_type=NotifyType.HEAD_ASSIGNED, kam=kam, head=head, actor=actor)
        return supervision

    @transaction.atomic
    def remove_supervisor(self, kam: AbstractBaseUser, actor: AbstractBaseUser | None) -> Supervision | None:
        """Снимает руководителя КАМа; возвращает удалённую связь или None, если её не было."""
        self._lock_kam(kam)
        supervision = Supervision.objects.select_related("kam", "head").filter(kam=kam).first()
        if supervision is None:
            return None
        supervision.delete()
        self._notify(notify_type=NotifyType.HEAD_UNASSIGNED, kam=supervision.kam, head=supervision.head, actor=actor)
        return supervision

    @transaction.atomic
    def claim(self, kam: AbstractBaseUser, head: AbstractBaseUser, actor: AbstractBaseUser | None) -> Supervision:
        """
        Руководитель забирает КАМа в команду; перехват чужого КАМа запрещён.

        Строка КАМа блокируется (`_lock_kam`): два руководителя, одновременно забирающие одного свободного КАМа,
        выполнятся по очереди, и второй получит `KamHasHeadError`, а не ошибку уникальности. Свой КАМ — no-op без
        уведомлений.
        """
        kam = self._lock_kam(kam)
        supervision = Supervision.objects.filter(kam=kam).first()
        if supervision is not None and supervision.head_id != head.pk:
            raise KamHasHeadError
        return self.set_supervisor(kam=kam, head=head, actor=actor)

    @transaction.atomic
    def release(self, kam: AbstractBaseUser, head: AbstractBaseUser, actor: AbstractBaseUser | None) -> Supervision:
        """Руководитель отпускает своего КАМа; КАМ становится свободным."""
        kam = self._lock_kam(kam)
        if not Supervision.objects.filter(kam=kam, head=head).exists():
            raise NotInTeamError
        return self.remove_supervisor(kam=kam, actor=actor)

    def kams_of(self, head: AbstractBaseUser) -> list[AbstractBaseUser]:
        """КАМы, у которых `head` записан руководителем, в порядке ФИО."""
        return [
            supervision.kam
            for supervision in Supervision.objects.select_related("kam")
            .filter(head=head)
            .order_by("kam__last_name", "kam__first_name", "kam__pk")
        ]

    @staticmethod
    def _lock_kam(kam: AbstractBaseUser) -> AbstractBaseUser:
        """
        Блокирует строку КАМа до конца транзакции и возвращает его свежую копию.

        Все изменения связи одного КАМа (назначение и снятие руководителя, claim/release) идут по очереди, а
        проверки роли и активности видят данные, записанные предыдущей транзакцией, а не объект из запроса.
        """
        return get_user_model().objects.select_for_update().get(pk=kam.pk)

    def _detach(self, user: AbstractBaseUser, actor: AbstractBaseUser | None) -> list[AbstractBaseUser]:
        """
        Удаляет все связи пользователя — и как КАМа, и как руководителя; возвращает КАМов, потерявших руководителя.

        Связи удаляются по обе стороны независимо от роли: так заодно убираются записи, устаревшие после изменений
        в обход сервиса.
        """
        self.remove_supervisor(kam=user, actor=actor)
        orphans = self.kams_of(head=user)
        Supervision.objects.filter(head=user).delete()
        for kam in orphans:
            self._notify(notify_type=NotifyType.HEAD_UNASSIGNED, kam=kam, head=user, actor=actor)
        return orphans

    @staticmethod
    def _notify(
        notify_type: str,
        kam: AbstractBaseUser,
        head: AbstractBaseUser,
        actor: AbstractBaseUser | None,
        to_kam: bool = True,
    ) -> None:
        """Уведомляет КАМа (если `to_kam`) и руководителя о назначении или снятии руководителя."""
        kam_name = kam.get_full_name() or kam.get_username()
        head_name = head.get_full_name() or head.get_username()
        if notify_type == NotifyType.HEAD_ASSIGNED:
            text = f"{kam_name} — в команде руководителя {head_name}"
        else:
            text = f"{kam_name} больше не в команде руководителя {head_name}"
        event_notification_service.notify(
            notify_type=notify_type,
            message=Message(text=text),
            responsible=kam if to_kam else None,
            head=head,
            actor=actor,
        )


account_service = AccountService()
