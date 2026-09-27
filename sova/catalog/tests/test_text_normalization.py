import importlib

from django.apps import apps as django_apps
from django.db import IntegrityError, transaction
from django.forms import modelform_factory
from django.test import TestCase

from sova.catalog.models import ContactPerson, Product, Program, University, Vendor
from sova.catalog.tests.factories import (
    ContactPersonFactory,
    UniversityContactFactory,
    DirectionFactory,
    UniversityFactory,
    VendorFactory,
)
from sova.core.text import normalize_text


class NormalizeTextTestCase(TestCase):
    """normalize_text убирает невидимые различия, но не трогает регистр."""

    def test_normalizes_whitespace_invisible_chars_and_unicode_form(self) -> None:
        value = " Сервис  Яндекс​ Облако й "

        self.assertEqual(normalize_text(value), "Сервис Яндекс Облако й")

    def test_keeps_case_and_line_breaks(self) -> None:
        self.assertEqual(normalize_text("мОсква\r\n  строка 2"), "мОсква\nстрока 2")


class ModelTextNormalizationTestCase(TestCase):
    """Текстовые поля справочников нормализуются при сохранении, регистр сохраняется как введён."""

    def test_vendor_name_and_code_are_normalized_on_save(self) -> None:
        vendor = Vendor.objects.create(name="мОсква  Софт ", external_code=" code​-1")

        vendor.refresh_from_db()
        self.assertEqual((vendor.name, vendor.external_code), ("мОсква Софт", "code-1"))

    def test_other_catalog_fields_are_normalized_on_save(self) -> None:
        university = UniversityFactory(name="МГУ ", short_name=" МГУ ")
        program = Program.objects.create(name="DevOps  инженер", direction=DirectionFactory())
        product = Product.objects.create(name="Docker​", external_code="p 1")
        contact = ContactPersonFactory(full_name="Иванов  Иван")
        link = UniversityContactFactory(contact=contact, university=university, position=" Проректор  по  науке ")

        self.assertEqual((university.name, university.short_name), ("МГУ", "МГУ"))
        self.assertEqual(program.name, "DevOps инженер")
        self.assertEqual((product.name, product.external_code), ("Docker", "p 1"))
        self.assertEqual(contact.full_name, "Иванов Иван")
        self.assertEqual(link.position, "Проректор по науке")


class CaseInsensitiveUniquenessTestCase(TestCase):
    """Уникальность названий, кодов и ФИО в БД — без учёта регистра."""

    def _assert_integrity_error(self, create) -> None:
        with transaction.atomic(), self.assertRaises(IntegrityError):
            create()

    def test_vendor_name_and_code(self) -> None:
        VendorFactory(name="Яндекс", external_code="YA")

        self._assert_integrity_error(lambda: VendorFactory(name="ЯНДЕКС"))
        self._assert_integrity_error(lambda: VendorFactory(external_code="ya"))

    def test_university_name(self) -> None:
        UniversityFactory(name="МГУ")

        self._assert_integrity_error(lambda: UniversityFactory(name="мгу"))

    def test_product_name_per_vendor_and_without_vendor(self) -> None:
        vendor = VendorFactory()
        Product.objects.create(name="Docker", vendor=vendor)
        Product.objects.create(name="Docker", vendor=VendorFactory())
        Product.objects.create(name="Kafka", vendor=None)

        self._assert_integrity_error(lambda: Product.objects.create(name="DOCKER", vendor=vendor))
        self._assert_integrity_error(lambda: Product.objects.create(name="kafka", vendor=None))

    def test_model_form_reports_case_insensitive_duplicate(self) -> None:
        """Формы (в том числе админки) видят нормализованное значение до проверки уникальности."""
        VendorFactory(name="Яндекс")
        form_class = modelform_factory(Vendor, fields=("name", "external_code", "is_active"))

        form = form_class(data={"name": "ЯНДЕКС ", "is_active": True})

        # Ограничение по выражению Lower("name") Django показывает общей ошибкой формы, не у поля.
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors(), ["Вендор с таким названием уже существует."])


class UniversityNameLookupTestCase(TestCase):
    """Смена регистра у самой записи — не конфликт с собой."""

    def test_record_can_change_own_case(self) -> None:
        university = UniversityFactory(name="мгу")

        university.name = "МГУ"
        university.full_clean()
        university.save()

        self.assertEqual(University.objects.get().name, "МГУ")


class NormalizeExistingValuesMigrationTestCase(TestCase):
    """Миграция 0007 нормализует уже сохранённые значения и останавливается на конфликтах."""

    migration = importlib.import_module("sova.catalog.migrations.0007_case_insensitive_uniqueness")

    def test_normalizes_existing_values(self) -> None:
        vendor = VendorFactory(name="Софт")
        # QuerySet.update идёт в обход нормализации модели — так в БД могли попасть старые значения.
        Vendor.objects.filter(pk=vendor.pk).update(name="Софт  Плюс")

        self.migration.normalize_existing_values(django_apps, schema_editor=None)

        vendor.refresh_from_db()
        self.assertEqual(vendor.name, "Софт Плюс")

    def test_conflict_stops_migration_with_list_and_saves_nothing(self) -> None:
        VendorFactory(name="Яндекс")
        other = VendorFactory(name="Другой")
        renamed = Program.objects.create(name="Курс", direction=DirectionFactory())
        Vendor.objects.filter(pk=other.pk).update(name="ЯНДЕКС ")
        Program.objects.filter(pk=renamed.pk).update(name="Курс  1")

        with self.assertRaises(RuntimeError) as context:
            self.migration.normalize_existing_values(django_apps, schema_editor=None)

        self.assertIn("«яндекс»", str(context.exception))
        self.assertIn(str(other.pk), str(context.exception))
        renamed.refresh_from_db()
        self.assertEqual(renamed.name, "Курс  1")
