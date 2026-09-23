from collections.abc import Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction
from django.utils import timezone

from sova.interactions.exceptions import AmbiguousManagerError, ManagerNotFoundError, NoActiveResponsibleError
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

    Менеджер из реестра договоров (ФИО строкой) не назначается автоматически: по ФИО подбирается
    пользователь-подсказка (`suggest_manager`), а назначение делает человек явно.
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
            unassigned_at__isnull=True,
        ).first()

    def _close(self, responsible: Responsible) -> None:
        """Закрывает назначение текущим моментом."""
        responsible.unassigned_at = timezone.now()
        responsible.save(update_fields=["unassigned_at"])

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).casefold()

    @classmethod
    def _name_variants(cls, user: AbstractBaseUser) -> set[str]:
        first, last = user.first_name, user.last_name
        return {cls._normalize(f"{first} {last}"), cls._normalize(f"{last} {first}")}


responsible_service = ResponsibleService()
