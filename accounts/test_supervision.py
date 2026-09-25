from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.exceptions import KamHasHeadError, NotInTeamError
from accounts.models import Supervision, SystemRole, UserRole
from accounts.services import account_service, get_system_role
from sova.core.tests.factories import UserFactory
from sova.notifications.enum import NotificationChannel


def create_user(role: str | None = None, **kwargs):
    """Создаёт пользователя и при необходимости назначает ему роль СОВА."""
    user = UserFactory(**kwargs)
    if role is not None:
        UserRole.objects.create(user=user, role=role)
    return user


class SupervisionCleanTestCase(TestCase):
    """Проверки связи «руководитель — КАМ» в `Supervision.clean`."""

    def setUp(self) -> None:
        """Активные КАМ и руководитель."""
        self.kam = create_user(SystemRole.KAM)
        self.head = create_user(SystemRole.HEAD)

    def assert_invalid(self, kam, head) -> None:
        """Связь не проходит проверку модели."""
        with self.assertRaises(ValidationError):
            Supervision(kam=kam, head=head).full_clean()

    def test_kam_and_head_are_valid(self) -> None:
        """КАМ и руководитель образуют допустимую связь."""
        Supervision(kam=self.kam, head=self.head).full_clean()

    def test_kam_must_have_kam_role(self) -> None:
        """Подчинённым может быть только КАМ."""
        self.assert_invalid(kam=create_user(SystemRole.HEAD), head=self.head)
        self.assert_invalid(kam=create_user(), head=self.head)

    def test_head_must_have_head_role(self) -> None:
        """Руководителем может быть только руководитель."""
        self.assert_invalid(kam=self.kam, head=create_user(SystemRole.PLATFORM_ADMIN))
        self.assert_invalid(kam=self.kam, head=create_user(SystemRole.KAM))

    def test_users_must_be_active(self) -> None:
        """Неактивного КАМа или руководителя связать нельзя."""
        self.assert_invalid(kam=create_user(SystemRole.KAM, is_active=False), head=self.head)
        self.assert_invalid(kam=self.kam, head=create_user(SystemRole.HEAD, is_active=False))

    def test_kam_has_single_head(self) -> None:
        """У КАМа не больше одного руководителя."""
        Supervision.objects.create(kam=self.kam, head=self.head)

        self.assert_invalid(kam=self.kam, head=create_user(SystemRole.HEAD))

    def test_head_has_many_kams(self) -> None:
        """У руководителя может быть несколько КАМов."""
        Supervision.objects.create(kam=self.kam, head=self.head)

        Supervision(kam=create_user(SystemRole.KAM), head=self.head).full_clean()


@patch("sova.notifications.services.event_notification.send_event_notification")
class AccountServiceTestCase(TestCase):
    """Смена роли, активности и руководителя через `account_service`: каскад связей и уведомления."""

    def setUp(self) -> None:
        """Администратор, руководитель с двумя КАМами и свободный руководитель."""
        self.admin = create_user(SystemRole.PLATFORM_ADMIN, first_name="Админ", last_name="Админов")
        self.head = create_user(SystemRole.HEAD, first_name="Анна", last_name="Смирнова")
        self.other_head = create_user(SystemRole.HEAD, first_name="Олег", last_name="Козлов")
        self.kam = create_user(SystemRole.KAM, first_name="Иван", last_name="Иванов")
        self.second_kam = create_user(SystemRole.KAM, first_name="Пётр", last_name="Петров")
        Supervision.objects.create(kam=self.kam, head=self.head)
        Supervision.objects.create(kam=self.second_kam, head=self.head)

    def run_service(self, method: str, **kwargs):
        """Вызывает метод сервиса с выполнением on_commit."""
        with self.captureOnCommitCallbacks(execute=True):
            return getattr(account_service, method)(**kwargs)

    @staticmethod
    def system_deliveries(task) -> list[tuple[str, list[int]]]:
        """Тексты и получатели постановок в колокольчик."""
        return [
            (item.kwargs["text"], sorted(item.kwargs["user_ids"]))
            for item in task.delay.call_args_list
            if item.kwargs["channels"] == [NotificationChannel.SYSTEM]
        ]

    def test_head_role_change_removes_team(self, task) -> None:
        """Руководитель стал КАМом — вся его команда осталась без руководителя, каждому уведомление."""
        orphans = self.run_service("change_role", user=self.head, role=SystemRole.KAM, actor=self.admin)

        # Проверяем, что роль сменилась, а связи удалены
        self.assertEqual(get_system_role(self.head), SystemRole.KAM)
        self.assertFalse(Supervision.objects.exists())
        # Проверяем возвращённых КАМов
        self.assertEqual(orphans, [self.kam, self.second_kam])
        # Проверяем уведомления КАМу и бывшему руководителю по каждой связи
        self.assertEqual(
            self.system_deliveries(task),
            [
                ("Иван Иванов больше не в команде руководителя Анна Смирнова", sorted([self.kam.pk, self.head.pk])),
                (
                    "Пётр Петров больше не в команде руководителя Анна Смирнова",
                    sorted([self.second_kam.pk, self.head.pk]),
                ),
            ],
        )

    def test_kam_role_change_removes_own_link(self, task) -> None:
        """КАМ стал руководителем — удаляется только его связь, осиротевших КАМов нет."""
        orphans = self.run_service("change_role", user=self.kam, role=SystemRole.HEAD, actor=self.admin)

        # Проверяем, что осталась только связь второго КАМа
        self.assertEqual(list(Supervision.objects.values_list("kam", flat=True)), [self.second_kam.pk])
        self.assertEqual(orphans, [])
        self.assertEqual(len(self.system_deliveries(task)), 1)

    def test_same_role_changes_nothing(self, task) -> None:
        """Сохранение той же роли не трогает связи и не шлёт уведомлений."""
        orphans = self.run_service("change_role", user=self.head, role=SystemRole.HEAD, actor=self.admin)

        # Проверяем, что связи на месте и уведомлений нет
        self.assertEqual(Supervision.objects.count(), 2)
        self.assertEqual(orphans, [])
        task.delay.assert_not_called()

    def test_role_removal(self, task) -> None:
        """Снятие роли удаляет `UserRole` и связи."""
        orphans = self.run_service("change_role", user=self.head, role=None, actor=self.admin)

        # Проверяем, что роли нет, а команда осталась без руководителя
        self.assertIsNone(get_system_role(self.head))
        self.assertFalse(UserRole.objects.filter(user=self.head).exists())
        self.assertEqual(orphans, [self.kam, self.second_kam])

    def test_role_assignment_to_user_without_role(self, task) -> None:
        """Пользователю без роли назначается роль."""
        user = create_user()

        self.run_service("change_role", user=user, role=SystemRole.KAM, actor=self.admin)

        self.assertEqual(get_system_role(user), SystemRole.KAM)

    def test_deactivate_head(self, task) -> None:
        """Деактивация руководителя удаляет связи его команды."""
        orphans = self.run_service("deactivate", user=self.head, actor=self.admin)

        self.head.refresh_from_db()
        # Проверяем, что пользователь неактивен и команда без руководителя
        self.assertFalse(self.head.is_active)
        self.assertFalse(Supervision.objects.exists())
        self.assertEqual(orphans, [self.kam, self.second_kam])
        # Проверяем, что неактивный бывший руководитель уведомлений не получает
        self.assertEqual(
            [user_ids for _, user_ids in self.system_deliveries(task)],
            [[self.kam.pk], [self.second_kam.pk]],
        )

    def test_deactivate_inactive_user_changes_nothing(self, task) -> None:
        """Повторная деактивация ничего не делает."""
        self.head.is_active = False
        self.head.save()

        orphans = self.run_service("deactivate", user=self.head, actor=self.admin)

        # Проверяем, что устаревшие связи не тронуты и уведомлений нет
        self.assertEqual(orphans, [])
        task.delay.assert_not_called()

    def test_activate(self, task) -> None:
        """Активация возвращает доступ, но не связи."""
        self.run_service("deactivate", user=self.kam, actor=self.admin)

        self.run_service("activate", user=self.kam, actor=self.admin)

        self.kam.refresh_from_db()
        self.assertTrue(self.kam.is_active)
        self.assertFalse(Supervision.objects.filter(kam=self.kam).exists())

    def test_set_supervisor_new(self, task) -> None:
        """Назначение руководителя КАМу без руководителя — уведомление КАМу и руководителю."""
        kam = create_user(SystemRole.KAM, first_name="Сергей", last_name="Сидоров")

        supervision = self.run_service("set_supervisor", kam=kam, head=self.other_head, actor=self.admin)

        # Проверяем связь и уведомление
        self.assertEqual((supervision.kam, supervision.head), (kam, self.other_head))
        self.assertEqual(
            self.system_deliveries(task),
            [("Сергей Сидоров — в команде руководителя Олег Козлов", sorted([kam.pk, self.other_head.pk]))],
        )

    def test_set_same_supervisor_changes_nothing(self, task) -> None:
        """Повторное назначение того же руководителя ничего не меняет."""
        self.run_service("set_supervisor", kam=self.kam, head=self.head, actor=self.admin)

        self.assertEqual(Supervision.objects.get(kam=self.kam).head, self.head)
        task.delay.assert_not_called()

    def test_change_supervisor(self, task) -> None:
        """Смена руководителя — прежнему уведомление о снятии, КАМу и новому — о назначении."""
        self.run_service("set_supervisor", kam=self.kam, head=self.other_head, actor=self.admin)

        # Проверяем, что связь одна и указывает на нового руководителя
        self.assertEqual(Supervision.objects.get(kam=self.kam).head, self.other_head)
        self.assertEqual(
            self.system_deliveries(task),
            [
                ("Иван Иванов больше не в команде руководителя Анна Смирнова", [self.head.pk]),
                ("Иван Иванов — в команде руководителя Олег Козлов", sorted([self.kam.pk, self.other_head.pk])),
            ],
        )

    def test_set_supervisor_validates_roles(self, task) -> None:
        """Руководителем нельзя назначить не-руководителя."""
        with self.assertRaises(ValidationError):
            account_service.set_supervisor(kam=self.kam, head=self.second_kam, actor=self.admin)

    def test_remove_supervisor(self, task) -> None:
        """Снятие руководителя удаляет связь и уведомляет обоих."""
        supervision = self.run_service("remove_supervisor", kam=self.kam, actor=self.admin)

        self.assertEqual(supervision.head, self.head)
        self.assertFalse(Supervision.objects.filter(kam=self.kam).exists())
        self.assertEqual(len(self.system_deliveries(task)), 1)

    def test_remove_missing_supervisor(self, task) -> None:
        """Снятие несуществующей связи возвращает None."""
        self.assertIsNone(self.run_service("remove_supervisor", kam=self.admin, actor=self.admin))
        task.delay.assert_not_called()

    def test_actor_is_not_notified(self, task) -> None:
        """Инициатор изменения уведомление не получает."""
        self.run_service("remove_supervisor", kam=self.kam, actor=self.head)

        self.assertEqual(self.system_deliveries(task)[0][1], [self.kam.pk])

    def test_kams_of(self, task) -> None:
        """КАМы руководителя в порядке ФИО."""
        self.assertEqual(account_service.kams_of(head=self.head), [self.kam, self.second_kam])
        self.assertEqual(account_service.kams_of(head=self.kam), [])


@patch("sova.notifications.services.event_notification.send_event_notification")
class TeamServiceTestCase(TestCase):
    """Руководитель забирает свободного КАМа и отпускает своего."""

    def setUp(self) -> None:
        """Два руководителя и свободный КАМ."""
        self.head = create_user(SystemRole.HEAD)
        self.other_head = create_user(SystemRole.HEAD)
        self.kam = create_user(SystemRole.KAM)

    def test_claim_free_kam(self, task) -> None:
        """Свободный КАМ попадает в команду руководителя."""
        supervision = account_service.claim(kam=self.kam, head=self.head, actor=self.head)

        # Проверяем, что связь создана с этим руководителем
        self.assertEqual(supervision.head, self.head)
        self.assertEqual(Supervision.objects.get(kam=self.kam).head, self.head)

    def test_claim_own_kam_is_noop(self, task) -> None:
        """Повторный claim своего КАМа ничего не меняет и не шлёт уведомлений."""
        account_service.claim(kam=self.kam, head=self.head, actor=self.head)
        task.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            account_service.claim(kam=self.kam, head=self.head, actor=self.head)

        # Проверяем, что связь одна и уведомлений нет
        self.assertEqual(Supervision.objects.filter(kam=self.kam).count(), 1)
        task.delay.assert_not_called()

    def test_claim_foreign_kam_raises(self, task) -> None:
        """КАМа с другим руководителем забрать нельзя."""
        account_service.claim(kam=self.kam, head=self.other_head, actor=self.other_head)

        with self.assertRaises(KamHasHeadError):
            account_service.claim(kam=self.kam, head=self.head, actor=self.head)

        # Проверяем, что связь осталась у прежнего руководителя
        self.assertEqual(Supervision.objects.get(kam=self.kam).head, self.other_head)

    def test_claim_not_kam_raises_validation_error(self, task) -> None:
        """Забрать в команду можно только КАМа."""
        with self.assertRaises(ValidationError):
            account_service.claim(kam=self.other_head, head=self.head, actor=self.head)

    def test_release_own_kam(self, task) -> None:
        """Руководитель отпускает своего КАМа — связь удаляется."""
        account_service.claim(kam=self.kam, head=self.head, actor=self.head)

        account_service.release(kam=self.kam, head=self.head, actor=self.head)

        # Проверяем, что КАМ свободен
        self.assertFalse(Supervision.objects.filter(kam=self.kam).exists())

    def test_release_foreign_kam_raises(self, task) -> None:
        """Чужого КАМа отпустить нельзя."""
        account_service.claim(kam=self.kam, head=self.other_head, actor=self.other_head)

        with self.assertRaises(NotInTeamError):
            account_service.release(kam=self.kam, head=self.head, actor=self.head)

        # Проверяем, что связь не тронута
        self.assertEqual(Supervision.objects.get(kam=self.kam).head, self.other_head)

    def test_release_free_kam_raises(self, task) -> None:
        """Свободного КАМа отпускать некому."""
        with self.assertRaises(NotInTeamError):
            account_service.release(kam=self.kam, head=self.head, actor=self.head)

    def test_claim_rechecks_kam_after_lock(self, task) -> None:
        """КАМа деактивировали, пока запрос ждал блокировку, — claim видит свежие данные и отказывает."""
        stale_kam = self.kam
        type(stale_kam).objects.filter(pk=stale_kam.pk).update(is_active=False)

        with self.assertRaises(ValidationError):
            account_service.claim(kam=stale_kam, head=self.head, actor=self.head)

        # Проверяем, что связь не создана
        self.assertFalse(Supervision.objects.filter(kam=self.kam).exists())

    def test_set_supervisor_rechecks_kam_after_lock(self, task) -> None:
        """Администратор назначает руководителя КАМу, которого только что деактивировали, — отказ."""
        stale_kam = self.kam
        type(stale_kam).objects.filter(pk=stale_kam.pk).update(is_active=False)

        with self.assertRaises(ValidationError):
            account_service.set_supervisor(kam=stale_kam, head=self.head, actor=None)
