from unittest.mock import patch

from django.contrib.messages import get_messages
from django.forms import MultiWidget
from django.test import TestCase
from django.urls import reverse

from accounts.models import Supervision, SystemRole, UserRole
from accounts.services import get_system_role
from accounts.test_supervision import create_user
from sova.core.tests.factories import UserFactory
from sova.notifications.enum import NotificationChannel


def form_data(form) -> dict:
    """POST-данные, которые браузер отправил бы для неизменённой формы."""
    data = {}
    for bound_field in form:
        if bound_field.field.disabled:
            continue
        value = bound_field.value()
        widget = bound_field.field.widget
        if isinstance(widget, MultiWidget):
            for index, part in enumerate(widget.decompress(value)):
                data[f"{bound_field.html_name}_{index}"] = "" if part is None else part
        elif isinstance(value, bool):
            if value:
                data[bound_field.html_name] = "on"
        elif value is not None:
            data[bound_field.html_name] = value
    return data


@patch("sova.notifications.services.event_notification.send_event_notification")
class AdminTestCase(TestCase):
    """Django Admin меняет роль, активность и руководителя через `account_service`."""

    def setUp(self) -> None:
        """Суперпользователь и руководитель с двумя КАМами."""
        self.superuser = UserFactory(is_staff=True, is_superuser=True)
        # Вход без OIDC: иначе middleware продления сессии уводит на Keycloak
        self.client.force_login(self.superuser, backend="django.contrib.auth.backends.ModelBackend")
        self.head = create_user(SystemRole.HEAD, first_name="Анна", last_name="Смирнова")
        self.kam = create_user(SystemRole.KAM, first_name="Иван", last_name="Иванов")
        self.second_kam = create_user(SystemRole.KAM, first_name="Пётр", last_name="Петров")
        Supervision.objects.create(kam=self.kam, head=self.head)
        Supervision.objects.create(kam=self.second_kam, head=self.head)

    def user_change_data(self, user) -> tuple[str, dict]:
        """Адрес и данные неизменённой карточки пользователя вместе с inline роли."""
        url = reverse("admin:auth_user_change", args=[user.pk])
        response = self.client.get(url)
        data = form_data(response.context["adminform"].form)
        for inline in response.context["inline_admin_formsets"]:
            formset = inline.formset
            data.update(form_data(formset.management_form))
            for form in formset.forms:
                data.update(form_data(form))
        return url, data

    def post(self, url: str, data: dict):
        """Отправляет форму с выполнением on_commit и проверяет, что она сохранилась."""
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, data, follow=True)
        # Проверяем, что форма без ошибок
        self.assertIsNone(response.context.get("errors") or None, response.context.get("errors"))
        return response

    @staticmethod
    def system_count(task) -> int:
        """Число постановок уведомлений в колокольчик: у каждого уведомления одна такая постановка."""
        return sum(item.kwargs["channels"] == [NotificationChannel.SYSTEM] for item in task.delay.call_args_list)

    @staticmethod
    def warnings(response) -> list[str]:
        """Тексты сообщений уровня warning."""
        return [message.message for message in get_messages(response.wsgi_request) if message.level_tag == "warning"]

    def test_role_change_in_user_card_removes_team(self, task) -> None:
        """Смена роли руководителя в карточке пользователя удаляет его команду и предупреждает."""
        url, data = self.user_change_data(self.head)
        data["system_role-0-role"] = SystemRole.KAM

        response = self.post(url, data)

        # Проверяем, что роль сменилась, связи удалены, КАМы уведомлены
        self.assertEqual(get_system_role(UserRole.objects.get(user=self.head).user), SystemRole.KAM)
        self.assertFalse(Supervision.objects.exists())
        self.assertEqual(self.system_count(task), 2)
        # Проверяем предупреждение со списком КАМов
        self.assertEqual(
            self.warnings(response),
            ["Команда «Анна Смирнова» осталась без руководителя: Иван Иванов, Пётр Петров"],
        )

    def test_role_removal_in_user_card(self, task) -> None:
        """Удаление роли в карточке пользователя удаляет роль и связи."""
        url, data = self.user_change_data(self.head)
        data["system_role-0-DELETE"] = "on"

        self.post(url, data)

        self.assertFalse(UserRole.objects.filter(user=self.head).exists())
        self.assertFalse(Supervision.objects.exists())

    def test_role_assignment_in_user_card(self, task) -> None:
        """Роль назначается пользователю без роли из карточки."""
        user = create_user()
        url, data = self.user_change_data(user)
        data.update({"system_role-TOTAL_FORMS": "1", "system_role-0-role": SystemRole.KAM})

        self.post(url, data)

        self.assertEqual(UserRole.objects.get(user=user).role, SystemRole.KAM)

    def test_deactivation_in_user_card_removes_team(self, task) -> None:
        """Снятие флага «Активный» у руководителя удаляет его команду и предупреждает."""
        url, data = self.user_change_data(self.head)
        del data["is_active"]

        response = self.post(url, data)

        self.head.refresh_from_db()
        # Проверяем, что руководитель неактивен, а связи удалены
        self.assertFalse(self.head.is_active)
        self.assertFalse(Supervision.objects.exists())
        self.assertEqual(len(self.warnings(response)), 1)

    def test_unchanged_user_card_keeps_team(self, task) -> None:
        """Сохранение карточки без изменений не трогает связи."""
        url, data = self.user_change_data(self.head)

        response = self.post(url, data)

        # Проверяем, что связи на месте и уведомлений нет
        self.assertEqual(Supervision.objects.count(), 2)
        task.delay.assert_not_called()
        self.assertEqual(self.warnings(response), [])

    def test_user_card_shows_team(self, task) -> None:
        """В карточке руководителя видна команда, в карточке КАМа — руководитель."""
        head_page = self.client.get(reverse("admin:auth_user_change", args=[self.head.pk]))
        kam_page = self.client.get(reverse("admin:auth_user_change", args=[self.kam.pk]))

        self.assertContains(head_page, "Иван Иванов, Пётр Петров")
        self.assertContains(kam_page, "Анна Смирнова")

    def test_user_deletion_warns_about_team(self, task) -> None:
        """Удаление руководителя предупреждает о команде без руководителя."""
        url = reverse("admin:auth_user_delete", args=[self.head.pk])

        response = self.post(url, {"post": "yes"})

        self.assertFalse(Supervision.objects.exists())
        self.assertEqual(len(self.warnings(response)), 1)

    def test_user_role_admin_change(self, task) -> None:
        """Смена роли в админке ролей удаляет команду руководителя."""
        assignment = UserRole.objects.get(user=self.head)
        url = reverse("admin:accounts_userrole_change", args=[assignment.pk])

        response = self.post(url, {"role": SystemRole.PLATFORM_ADMIN})

        self.assertEqual(UserRole.objects.get(user=self.head).role, SystemRole.PLATFORM_ADMIN)
        self.assertFalse(Supervision.objects.exists())
        self.assertEqual(len(self.warnings(response)), 1)

    def test_user_role_admin_delete(self, task) -> None:
        """Удаление роли в админке ролей удаляет команду руководителя."""
        assignment = UserRole.objects.get(user=self.head)
        url = reverse("admin:accounts_userrole_delete", args=[assignment.pk])

        self.post(url, {"post": "yes"})

        self.assertFalse(UserRole.objects.filter(user=self.head).exists())
        self.assertFalse(Supervision.objects.exists())

    def test_user_role_admin_bulk_delete(self, task) -> None:
        """Массовое удаление ролей удаляет и связи."""
        url = reverse("admin:accounts_userrole_changelist")
        ids = [str(UserRole.objects.get(user=self.head).pk)]

        self.post(url, {"action": "delete_selected", "_selected_action": ids, "post": "yes"})

        self.assertFalse(Supervision.objects.exists())

    def test_supervision_admin_add(self, task) -> None:
        """Назначение руководителя в админке — через сервис, с уведомлением."""
        kam = create_user(SystemRole.KAM)

        self.post(reverse("admin:accounts_supervision_add"), {"kam": kam.pk, "head": self.head.pk})

        self.assertTrue(Supervision.objects.filter(kam=kam, head=self.head).exists())
        self.assertEqual(self.system_count(task), 1)

    def test_supervision_admin_rejects_wrong_role(self, task) -> None:
        """Руководителем нельзя выбрать КАМа."""
        kam = create_user(SystemRole.KAM)

        response = self.client.post(
            reverse("admin:accounts_supervision_add"),
            {"kam": kam.pk, "head": self.kam.pk},
        )

        # Проверяем, что форма вернулась с ошибкой
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Supervision.objects.filter(kam=kam).exists())

    def test_supervision_admin_change_head(self, task) -> None:
        """Смена руководителя в админке — уведомления прежнему и новому."""
        other_head = create_user(SystemRole.HEAD)
        supervision = Supervision.objects.get(kam=self.kam)
        url = reverse("admin:accounts_supervision_change", args=[supervision.pk])

        self.post(url, {"head": other_head.pk})

        self.assertEqual(Supervision.objects.get(kam=self.kam).head, other_head)
        self.assertEqual(self.system_count(task), 2)

    def test_supervision_admin_delete(self, task) -> None:
        """Удаление связи в админке — через сервис, с уведомлением."""
        supervision = Supervision.objects.get(kam=self.kam)

        self.post(reverse("admin:accounts_supervision_delete", args=[supervision.pk]), {"post": "yes"})

        self.assertFalse(Supervision.objects.filter(kam=self.kam).exists())
        self.assertEqual(self.system_count(task), 1)

    def test_supervision_admin_bulk_delete(self, task) -> None:
        """Массовое удаление связей — через сервис, уведомление по каждой."""
        ids = [str(pk) for pk in Supervision.objects.values_list("pk", flat=True)]

        self.post(
            reverse("admin:accounts_supervision_changelist"),
            {"action": "delete_selected", "_selected_action": ids, "post": "yes"},
        )

        self.assertFalse(Supervision.objects.exists())
        self.assertEqual(self.system_count(task), 2)
