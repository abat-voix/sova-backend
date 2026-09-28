from django.db import IntegrityError, transaction
from django.test import TestCase

from sova.catalog.enum import ContactChannel
from sova.catalog.models import ContactPerson, OrganizationContact
from sova.catalog.tests.factories import (
    ContactPersonFactory,
    ProductFactory,
    OrganizationContactFactory,
    VendorContactFactory,
    VendorFactory,
)


class ContactAffiliationModelTestCase(TestCase):
    """Человек связан с несколькими организациями, у каждой связи своя должность."""

    def test_person_with_two_organizations_and_vendor(self) -> None:
        contact = ContactPersonFactory()
        OrganizationContactFactory(contact=contact, position="Проректор")
        OrganizationContactFactory(contact=contact, position="Доцент")
        vendor_link = VendorContactFactory(
            contact=contact,
            position="Консультант",
            preferred_channels=[ContactChannel.EMAIL, ContactChannel.TELEGRAM],
        )

        self.assertEqual(
            sorted(contact.organization_links.values_list("position", flat=True)), ["Доцент", "Проректор"]
        )
        vendor_link.refresh_from_db()
        self.assertEqual(vendor_link.preferred_channels, ["email", "telegram"])

    def test_affiliation_has_no_activity_or_dates(self) -> None:
        """Связь либо есть, либо её нет: активность — только у человека."""
        field_names = {field.name for field in OrganizationContact._meta.get_fields()}

        self.assertFalse({"is_active", "started_at", "ended_at"} & field_names)

    def test_one_affiliation_per_pair(self) -> None:
        link = OrganizationContactFactory()

        with transaction.atomic(), self.assertRaises(IntegrityError):
            OrganizationContactFactory(contact=link.contact, organization=link.organization)

    def test_vendor_contact_products(self) -> None:
        vendor = VendorFactory()
        product = ProductFactory(vendor=vendor)

        link = VendorContactFactory(vendor=vendor, products=[product])

        self.assertEqual(list(link.products.all()), [product])

    def test_position_is_normalized(self) -> None:
        link = OrganizationContactFactory(position=" Проректор  по  науке ")

        self.assertEqual(link.position, "Проректор по науке")

    def test_person_with_links_cannot_be_deleted_directly(self) -> None:
        link = OrganizationContactFactory()

        with transaction.atomic(), self.assertRaises(IntegrityError):
            ContactPerson.objects.filter(pk=link.contact_id).delete()

