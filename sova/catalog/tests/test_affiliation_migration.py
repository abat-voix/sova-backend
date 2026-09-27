from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("catalog", "0008_contact_affiliations")]
AFTER = [("catalog", "0009_remove_affiliation_periods")]


class RemoveAffiliationPeriodsMigrationTestCase(TransactionTestCase):
    """Миграция 0009 оставляет одну связь на пару, даже если у пары было несколько периодов."""

    def setUp(self) -> None:
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(BEFORE)
        self.apps = self.executor.loader.project_state(BEFORE).apps

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_vendor_pair_with_closed_and_active_periods_keeps_active(self) -> None:
        ContactPerson = self.apps.get_model("catalog", "ContactPerson")
        Vendor = self.apps.get_model("catalog", "Vendor")
        Product = self.apps.get_model("catalog", "Product")
        VendorContact = self.apps.get_model("catalog", "VendorContact")
        contact = ContactPerson.objects.create(full_name="Иванов Иван")
        vendor = Vendor.objects.create(name="ООО «Базис»")
        product = Product.objects.create(name="Базис Dynamix", vendor=vendor)
        closed = VendorContact.objects.create(
            contact=contact,
            vendor=vendor,
            position="Консультант",
            is_active=False,
            started_at=date(2025, 1, 1),
            ended_at=date(2025, 6, 30),
        )
        closed.products.set([product])
        active = VendorContact.objects.create(contact=contact, vendor=vendor, position="Архитектор")

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)

        migrated = executor.loader.project_state(AFTER).apps.get_model("catalog", "VendorContact")
        self.assertEqual(list(migrated.objects.values_list("pk", "position")), [(active.pk, "Архитектор")])
