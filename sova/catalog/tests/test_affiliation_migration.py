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


class RemoveOtherContactChannelMigrationTestCase(TransactionTestCase):
    """Миграция 0010 убирает способ связи «Другое», остальные способы связи сохраняются."""

    before = [("catalog", "0009_remove_affiliation_periods")]
    after = [("catalog", "0010_remove_other_contact_channel")]

    def setUp(self) -> None:
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.before)
        self.apps = self.executor.loader.project_state(self.before).apps

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_other_channel_is_removed(self) -> None:
        ContactPerson = self.apps.get_model("catalog", "ContactPerson")
        University = self.apps.get_model("catalog", "University")
        UniversityContact = self.apps.get_model("catalog", "UniversityContact")
        link = UniversityContact.objects.create(
            contact=ContactPerson.objects.create(full_name="Иванов Иван"),
            university=University.objects.create(name="МГУ"),
            preferred_channels=["email", "other", "telegram"],
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.after)

        migrated = executor.loader.project_state(self.after).apps.get_model("catalog", "UniversityContact")
        self.assertEqual(migrated.objects.get(pk=link.pk).preferred_channels, ["email", "telegram"])
