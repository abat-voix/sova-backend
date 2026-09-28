from unittest.mock import patch

from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.models import ContactPerson, OrganizationContact, VendorContact
from sova.catalog.services import contact_affiliation_service
from sova.catalog.tests.factories import OrganizationContactFactory, OrganizationFactory, VendorContactFactory
from sova.core.tests.factories import UserFactory
from sova.interactions.models import InteractionContact
from sova.interactions.tests.factories import InteractionFactory, ResponsibleFactory
from sova.notifications.enum import NotificationChannel


def _system_calls(task) -> list:
    """Постановки уведомлений в колокольчик."""
    return [item.kwargs for item in task.delay.call_args_list if item.kwargs["channels"] == [NotificationChannel.SYSTEM]]


@patch("sova.notifications.services.event_notification.send_event_notification")
class AffiliationDeletionTestCase(TestCase):
    """Человек ушёл из вуза: связь удаляется, привязки к активным взаимодействиям вуза закрываются, КАМы уведомлены."""

    def setUp(self) -> None:
        self.link = OrganizationContactFactory(contact__full_name="Иванов Иван", position="Проректор")
        self.interaction = InteractionFactory(organization=self.link.organization)
        self.kams = ResponsibleFactory.create_batch(2, interaction=self.interaction)
        self.actor = UserFactory()
        InteractionContact.objects.create(interaction=self.interaction, contact_person=self.link.contact)

    def _delete(self, affiliation=None) -> list:
        with self.captureOnCommitCallbacks(execute=True):
            return contact_affiliation_service.delete(affiliation=affiliation or self.link, actor=self.actor)

    def test_delete_unlinks_and_notifies_active_kams(self, task) -> None:
        closed = self._delete()

        self.assertFalse(OrganizationContact.objects.exists())
        self.assertEqual(len(closed), 1)
        link = InteractionContact.objects.get()
        self.assertIsNotNone(link.unlinked_at)
        self.assertEqual(link.unlinked_by, self.actor)
        calls = _system_calls(task)
        self.assertEqual(sorted(call["user_ids"][0] for call in calls), sorted(kam.manager_id for kam in self.kams))
        self.assertIn("Иванов Иван больше не работает", calls[0]["text"])
        self.assertIn("не осталось контактных лиц", calls[0]["text"])

    def test_inactive_interaction_is_left_as_is(self, task) -> None:
        """Завершённое (неактивное) взаимодействие хранит своих контактов: отвязки и уведомления нет."""
        finished = InteractionFactory(organization=self.link.organization, is_active=False)
        ResponsibleFactory(interaction=finished)
        InteractionContact.objects.create(interaction=finished, contact_person=self.link.contact)

        self._delete()

        self.assertTrue(InteractionContact.objects.filter(interaction=finished, unlinked_at__isnull=True).exists())
        self.assertEqual(len(_system_calls(task)), len(self.kams))

    def test_other_organization_links_are_kept(self, task) -> None:
        other = OrganizationContactFactory(contact=self.link.contact)
        other_interaction = InteractionFactory(organization=other.organization)
        InteractionContact.objects.create(interaction=other_interaction, contact_person=self.link.contact)

        self._delete()

        self.assertTrue(
            InteractionContact.objects.filter(interaction=other_interaction, unlinked_at__isnull=True).exists()
        )

    def test_vendor_affiliation_is_just_deleted(self, task) -> None:
        link = VendorContactFactory(contact=self.link.contact)

        closed = self._delete(affiliation=link)

        self.assertEqual(closed, [])
        self.assertFalse(VendorContact.objects.exists())
        self.assertTrue(InteractionContact.objects.filter(unlinked_at__isnull=True).exists())


@patch("sova.notifications.services.event_notification.send_event_notification")
class ContactDeactivationServiceTestCase(TestCase):
    """Выключение человека — ушёл отовсюду: привязки ко всем активным взаимодействиям закрыты, связи удалены."""

    def setUp(self) -> None:
        self.first = OrganizationContactFactory()
        self.contact = self.first.contact
        self.second = OrganizationContactFactory(contact=self.contact)
        VendorContactFactory(contact=self.contact)
        for link in (self.first, self.second):
            interaction = InteractionFactory(organization=link.organization)
            ResponsibleFactory(interaction=interaction)
            InteractionContact.objects.create(interaction=interaction, contact_person=self.contact)

    def test_deactivate_contact_unlinks_everywhere_and_deletes_affiliations(self, task) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            closed = contact_affiliation_service.deactivate_contact(contact=self.contact)

        self.contact.refresh_from_db()
        self.assertFalse(self.contact.is_active)
        self.assertEqual(len(closed), 2)
        self.assertFalse(OrganizationContact.objects.filter(contact=self.contact).exists())
        self.assertFalse(VendorContact.objects.filter(contact=self.contact).exists())
        self.assertFalse(InteractionContact.objects.filter(unlinked_at__isnull=True).exists())
        self.assertEqual(len(_system_calls(task)), 2)

    def test_deactivate_contact_clears_prefetched_affiliations(self, task) -> None:
        """Ответ API после выключения строится из того же объекта — предзагруженные связи не должны остаться."""
        contact = contact_affiliation_service.prefetch_links(ContactPerson.objects.all()).get(pk=self.contact.pk)
        self.assertEqual(len(contact_affiliation_service.links_of(contact=contact)), 3)

        contact_affiliation_service.deactivate_contact(contact=contact)

        self.assertEqual(contact_affiliation_service.links_of(contact=contact), [])

    def test_deactivate_contact_skips_inactive_interactions(self, task) -> None:
        finished = InteractionFactory(organization=self.first.organization, is_active=False)
        InteractionContact.objects.create(interaction=finished, contact_person=self.contact)

        contact_affiliation_service.deactivate_contact(contact=self.contact)

        self.assertTrue(InteractionContact.objects.filter(interaction=finished, unlinked_at__isnull=True).exists())

    def test_activate_contact_does_not_bring_affiliations_back(self, task) -> None:
        contact_affiliation_service.deactivate_contact(contact=self.contact)

        contact_affiliation_service.activate_contact(contact=self.contact)

        self.contact.refresh_from_db()
        self.assertTrue(self.contact.is_active)
        self.assertFalse(OrganizationContact.objects.filter(contact=self.contact).exists())
        # Закрытые привязки не восстанавливаются
        self.assertFalse(InteractionContact.objects.filter(unlinked_at__isnull=True).exists())


@patch("sova.notifications.services.event_notification.send_event_notification")
class AffiliationApiTestCase(APITestCase):
    """CRUD связи: удаление — уход из организации, активности и дат у связи нет."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)
        self.link = OrganizationContactFactory(position="Проректор")
        interaction = InteractionFactory(organization=self.link.organization)
        ResponsibleFactory(interaction=interaction)
        InteractionContact.objects.create(interaction=interaction, contact_person=self.link.contact)
        self.url = reverse("catalog:organization-contact-detail", args=[self.link.pk])

    def test_delete_unlinks_and_returns_204(self, task) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(OrganizationContact.objects.exists())
        self.assertEqual(InteractionContact.objects.get().unlinked_by, self.user)
        self.assertEqual(len(_system_calls(task)), 1)

    def test_patch_position_does_not_unlink(self, task) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(self.url, {"position": "Декан"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data["position"], "Декан")
        self.assertTrue(InteractionContact.objects.filter(unlinked_at__isnull=True).exists())
        self.assertEqual(_system_calls(task), [])

    def test_response_has_no_activity_or_dates(self, task) -> None:
        response = self.client.get(self.url)

        self.assertFalse({"is_active", "started_at", "ended_at"} & set(response.data))

    def test_create_affiliation_for_inactive_contact_turns_it_on(self, task) -> None:
        contact = OrganizationContactFactory(contact__is_active=False).contact
        organization = OrganizationContactFactory().organization

        response = self.client.post(
            reverse("catalog:organization-contact-list"),
            {"contact": str(contact.pk), "organization": str(organization.pk), "position": "Доцент"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, msg=response.data)
        contact.refresh_from_db()
        self.assertTrue(contact.is_active)

    def test_second_affiliation_of_pair_returns_400(self, task) -> None:
        response = self.client.post(
            reverse("catalog:organization-contact-list"),
            {"contact": str(self.link.contact_id), "organization": str(self.link.organization_id)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_contact_activity(self, task) -> None:
        OrganizationContactFactory(organization=self.link.organization, contact__is_active=False)

        response = self.client.get(
            reverse("catalog:organization-contact-list"),
            {"organization__ids": str(self.link.organization_id), "contact__is_active": "true"},
        )

        self.assertEqual([item["id"] for item in response.data["results"]], [str(self.link.pk)])

    def test_restore_endpoint_is_removed(self, task) -> None:
        with self.assertRaises(NoReverseMatch):
            reverse("catalog:organization-contact-restore", args=[self.link.pk])


@patch("sova.notifications.services.event_notification.send_event_notification")
class ContactDeactivationApiTestCase(APITestCase):
    """PATCH is_active у человека: выключение отвязывает отовсюду и удаляет связи; включение связей не возвращает."""

    def setUp(self) -> None:
        self.user = UserFactory()
        UserRole.objects.create(user=self.user, role=SystemRole.PLATFORM_ADMIN)
        self.client.force_authenticate(user=self.user)
        self.link = OrganizationContactFactory()
        self.contact = self.link.contact
        self.vendor_link = VendorContactFactory(contact=self.contact)
        self.interaction = InteractionFactory(organization=self.link.organization)
        ResponsibleFactory(interaction=self.interaction)
        InteractionContact.objects.create(interaction=self.interaction, contact_person=self.contact)
        self.url = reverse("catalog:contact-person-detail", args=[self.contact.pk])

    def test_patch_deactivates_contact_and_deletes_affiliations(self, task) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(self.url, {"is_active": False}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertFalse(response.data["is_active"])
        self.assertEqual(response.data["affiliations"], [])
        self.assertFalse(OrganizationContact.objects.exists())
        self.assertFalse(VendorContact.objects.exists())
        self.assertEqual(InteractionContact.objects.get().unlinked_by, self.user)
        self.assertEqual(len(_system_calls(task)), 1)

    def test_reactivated_contact_needs_new_affiliation(self, task) -> None:
        """Включённого человека без новой связи не привязать; создали связь с вузом — привязывается."""
        link_url = reverse("interactions:interaction-contacts", args=[self.interaction.pk])
        self.client.patch(self.url, {"is_active": False}, format="json")
        self.client.patch(self.url, {"is_active": True}, format="json")

        without_affiliation = self.client.post(link_url, {"contact_person": str(self.contact.pk)}, format="json")
        self.client.post(
            reverse("catalog:organization-contact-list"),
            {"contact": str(self.contact.pk), "organization": str(self.interaction.organization_id)},
            format="json",
        )
        with_affiliation = self.client.post(link_url, {"contact_person": str(self.contact.pk)}, format="json")

        self.assertEqual(without_affiliation.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(with_affiliation.status_code, status.HTTP_200_OK, msg=with_affiliation.data)


@patch("sova.notifications.services.event_notification.send_event_notification")
class AffiliationAdminTestCase(TestCase):
    """Inline связей в админке: удаление — через сервис связей, новая связь включает человека."""

    def setUp(self) -> None:
        self.client.force_login(UserFactory(is_staff=True, is_superuser=True))
        self.link = OrganizationContactFactory(position="Проректор")
        interaction = InteractionFactory(organization=self.link.organization)
        InteractionContact.objects.create(interaction=interaction, contact_person=self.link.contact)
        self.url = reverse("admin:catalog_contactperson_change", args=[self.link.contact_id])

    def _post(self, contact_active: bool = True, extra: dict | None = None, **link_fields) -> None:
        contact = self.link.contact
        prefix = "organization_links"
        forms = [
            {
                "id": str(self.link.pk),
                "contact": str(contact.pk),
                "organization": str(self.link.organization_id),
                "position": "Проректор",
                "preferred_channels": "",
                **link_fields,
            }
        ]
        if extra is not None:
            forms.append({"id": "", "contact": str(contact.pk), "preferred_channels": "", **extra})
        data = {
            "full_name": contact.full_name,
            "email": "",
            "phone": "",
            "telegram": "",
            f"{prefix}-TOTAL_FORMS": str(len(forms)),
            f"{prefix}-INITIAL_FORMS": "1",
        }
        for index, form in enumerate(forms):
            data.update({f"{prefix}-{index}-{key}": value for key, value in form.items()})
        if contact_active:
            data["is_active"] = "on"
        for other in ("b2c_client_links", "vendor_links"):
            data.update({f"{other}-TOTAL_FORMS": "0", f"{other}-INITIAL_FORMS": "0"})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)

    def test_inline_delete_unlinks(self, task) -> None:
        self._post(DELETE="on")

        self.assertFalse(OrganizationContact.objects.exists())
        self.assertFalse(InteractionContact.objects.filter(unlinked_at__isnull=True).exists())

    def test_inline_new_affiliation_turns_contact_on(self, task) -> None:
        ContactPerson.objects.filter(pk=self.link.contact_id).update(is_active=False)

        self._post(contact_active=False, extra={"organization": str(OrganizationFactory().pk), "position": "Доцент"})

        self.assertTrue(ContactPerson.objects.get(pk=self.link.contact_id).is_active)
        self.assertEqual(OrganizationContact.objects.filter(contact_id=self.link.contact_id).count(), 2)

    def test_contact_off_and_new_affiliation_in_one_form_leaves_contact_off(self, task) -> None:
        self._post(contact_active=False, extra={"organization": str(OrganizationFactory().pk), "position": "Доцент"})

        self.assertFalse(ContactPerson.objects.get(pk=self.link.contact_id).is_active)
        self.assertFalse(OrganizationContact.objects.filter(contact_id=self.link.contact_id).exists())
        self.assertFalse(InteractionContact.objects.filter(unlinked_at__isnull=True).exists())

    def test_inline_cannot_move_affiliation_to_other_organization(self, task) -> None:
        """Другая организация — другая связь: у существующей строки вуз не меняется, привязки не повисают."""
        organization = self.link.organization

        self._post(organization=str(OrganizationFactory().pk))

        self.link.refresh_from_db()
        self.assertEqual(self.link.organization_id, organization.pk)
