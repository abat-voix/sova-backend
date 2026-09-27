from django.test import TestCase

from sova.catalog.exceptions import CatalogImportError
from sova.catalog.models import UniversityContact, VendorContact
from sova.catalog.services import contact_affiliation_service, contact_matching_service
from sova.catalog.tests.factories import (
    B2CClientContactFactory,
    ContactPersonFactory,
    ProductFactory,
    UniversityContactFactory,
    UniversityFactory,
    VendorContactFactory,
    VendorFactory,
)
from sova.interactions.models import InteractionContact
from sova.interactions.tests.factories import InteractionFactory


class ContactAffiliationServiceTestCase(TestCase):
    """Сервис связей выбирает модель по типу организации и хранит должность в связи."""

    def test_create_contact_with_affiliation_per_organization_type(self) -> None:
        for organization, model in (
            (UniversityFactory(), UniversityContact),
            (VendorFactory(), VendorContact),
        ):
            with self.subTest(model=model.__name__):
                link = contact_affiliation_service.create_contact(
                    organization=organization, full_name="Иванов Иван", position="Проректор"
                )

                self.assertIsInstance(link, model)
                self.assertEqual(contact_affiliation_service.organization_of(affiliation=link), organization)
                self.assertEqual(
                    contact_affiliation_service.position_for(contact=link.contact, organization=organization),
                    "Проректор",
                )

    def test_position_depends_on_organization(self) -> None:
        contact = ContactPersonFactory()
        first = UniversityContactFactory(contact=contact, position="Проректор").university
        second = UniversityContactFactory(contact=contact, position="Доцент").university

        self.assertEqual(contact_affiliation_service.position_for(contact=contact, organization=first), "Проректор")
        self.assertEqual(contact_affiliation_service.position_for(contact=contact, organization=second), "Доцент")
        self.assertEqual(contact_affiliation_service.position_for(contact=contact, organization=VendorFactory()), "")

    def test_contacts_for_organization(self) -> None:
        link = UniversityContactFactory()
        UniversityContactFactory()

        self.assertEqual(
            list(contact_affiliation_service.contacts_for(organization=link.university)), [link.contact]
        )

    def test_set_products_rejects_foreign_vendor(self) -> None:
        link = VendorContactFactory()
        own = ProductFactory(vendor=link.vendor)

        contact_affiliation_service.set_products(affiliation=link, products=[own])
        with self.assertRaises(ValueError):
            contact_affiliation_service.set_products(affiliation=link, products=[ProductFactory()])

        self.assertEqual(list(link.products.all()), [own])

    def test_annotate_interaction_position(self) -> None:
        contact = ContactPersonFactory()
        university_link = UniversityContactFactory(contact=contact, position="Проректор")
        UniversityContactFactory(contact=contact, position="Доцент")
        client_link = B2CClientContactFactory(contact=contact, position="Директор")
        university_interaction = InteractionFactory(university=university_link.university)
        client_interaction = InteractionFactory(university=None, b2c_client=client_link.b2c_client)
        InteractionContact.objects.create(interaction=university_interaction, contact_person=contact)
        InteractionContact.objects.create(interaction=client_interaction, contact_person=contact)

        positions = dict(
            contact_affiliation_service.annotate_interaction_position(InteractionContact.objects.all()).values_list(
                "interaction_id", "position"
            )
        )

        self.assertEqual(
            positions, {university_interaction.pk: "Проректор", client_interaction.pk: "Директор"}
        )

    def test_unknown_organization_type(self) -> None:
        with self.assertRaises(ValueError):
            contact_affiliation_service.contacts_for(organization=ContactPersonFactory())


class ContactMatchingServiceTestCase(TestCase):
    """Сопоставление человека при импорте: email → тёзка в организации → новый человек."""

    def test_email_finds_person_of_other_organization(self) -> None:
        link = UniversityContactFactory(contact__email="ivanov@example.ru")

        match = contact_matching_service.match_for_import(
            organization=VendorFactory(), full_name="Иванов И. И.", email="IVANOV@example.ru"
        )

        self.assertEqual(match.contact, link.contact)

    def test_namesake_in_same_organization(self) -> None:
        link = UniversityContactFactory(contact__full_name="Иванов Иван")

        match = contact_matching_service.match_for_import(organization=link.university, full_name="иванов иван")

        self.assertEqual(match.contact, link.contact)

    def test_namesake_in_other_organization_is_new_person_with_duplicate_hint(self) -> None:
        link = UniversityContactFactory(contact__full_name="Иванов Иван")

        match = contact_matching_service.match_for_import(organization=UniversityFactory(), full_name="Иванов Иван")

        self.assertIsNone(match.contact)
        self.assertEqual(match.possible_duplicates, [link.contact])

    def test_two_namesakes_narrowed_by_phone(self) -> None:
        university = UniversityFactory()
        UniversityContactFactory(university=university, contact__full_name="Иванов Иван", contact__phone="+7 900 1")
        target = UniversityContactFactory(
            university=university, contact__full_name="Иванов Иван", contact__phone="+7 (900) 111-22-33"
        )

        match = contact_matching_service.match_for_import(
            organization=university, full_name="Иванов Иван", phone="8 900 111 22 33"
        )

        self.assertEqual(match.contact, target.contact)

    def test_two_namesakes_without_hint_are_ambiguous(self) -> None:
        university = UniversityFactory()
        UniversityContactFactory.create_batch(2, university=university, contact__full_name="Иванов Иван")

        with self.assertRaises(CatalogImportError):
            contact_matching_service.match_for_import(organization=university, full_name="Иванов Иван")

    def test_possible_duplicates_by_phone_and_telegram(self) -> None:
        by_phone = ContactPersonFactory(phone="+7 (900) 111-22-33")
        by_telegram = ContactPersonFactory(telegram="Ivanov_II")
        ContactPersonFactory(phone="+7 (900) 999-22-33")

        duplicates = contact_matching_service.possible_duplicates(phone="89001112233", telegram="ivanov_ii")

        self.assertEqual({contact.pk for contact in duplicates}, {by_phone.pk, by_telegram.pk})

    def test_possible_duplicates_excludes_itself(self) -> None:
        contact = ContactPersonFactory(full_name="Иванов Иван")

        self.assertEqual(contact_matching_service.possible_duplicates(full_name="Иванов Иван", exclude_id=contact.pk), [])

    def test_b2c_client_is_supported(self) -> None:
        link = B2CClientContactFactory(contact__full_name="Петров Пётр")

        match = contact_matching_service.match_for_import(organization=link.b2c_client, full_name="Петров Пётр")

        self.assertEqual(match.contact, link.contact)
