from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import SystemRole, UserRole
from sova.catalog.enum import AddressKind, PersonalDataAccessAction
from sova.catalog.models import B2CClientAddress, B2CClientAddressAccessLog, OrganizationAddress
from sova.catalog.services import catalog_import_service, organization_address_service
from sova.catalog.tests.factories import B2CClientFactory, OrganizationFactory
from sova.core.tests.factories import UserFactory

MOSCOW = {"lat": "55.755864", "lon": "37.617698"}


def user_with_role(role: str):
    user = UserFactory()
    UserRole.objects.create(user=user, role=role)
    return user


def organization_row(**values) -> dict:
    """Строка справочника организаций с обязательными колонками."""
    row = dict.fromkeys(
        ("id", "name_en", "short_name", "country_code", "type", "works_count", "cited_by_count", "city", "region",
         "lat", "lon", "homepage_url"),
        "",
    )
    return {**row, "ror": "R-1", "name": "Вуз", **values}


class OrganizationAddressApiTestCase(APITestCase):
    """Юридический и фактический адреса организации в API каталога."""

    def setUp(self) -> None:
        self.client.force_authenticate(user_with_role(SystemRole.PLATFORM_ADMIN))

    def detail(self, organization) -> str:
        return reverse("catalog:organization-detail", args=(organization.pk,))

    def test_saves_both_addresses(self) -> None:
        organization = OrganizationFactory()

        response = self.client.patch(
            self.detail(organization),
            {
                "legal_address": {"city": "Москва", "street": "ул. Ленина", "house": "1", **MOSCOW},
                "actual_address": {"city": "Химки", "street": "ул. Мира", "house": "5"},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["legal_address"]["street"], "ул. Ленина")
        self.assertEqual(response.data["actual_address"]["city"], "Химки")
        self.assertEqual(organization.addresses.count(), 2)

    def test_actual_same_as_legal_is_not_stored_separately(self) -> None:
        organization = OrganizationFactory(city="Химки")

        response = self.client.patch(
            self.detail(organization),
            {"legal_address": {"city": "Москва", "street": "ул. Ленина"}, "actual_same_as_legal": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["actual_address"], response.data["legal_address"])
        self.assertEqual(list(organization.addresses.values_list("kind", flat=True)), [AddressKind.LEGAL])

    def test_null_removes_address(self) -> None:
        organization = OrganizationFactory(city="Химки")

        response = self.client.patch(self.detail(organization), {"actual_address": None}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNone(response.data["actual_address"])
        self.assertFalse(organization.addresses.exists())

    def test_coordinates_go_together_and_in_range(self) -> None:
        organization = OrganizationFactory()

        without_lon = self.client.patch(
            self.detail(organization), {"legal_address": {"lat": "55.75"}}, format="json"
        )
        out_of_range = self.client.patch(
            self.detail(organization), {"legal_address": {"lat": "95", "lon": "37"}}, format="json"
        )

        self.assertEqual(without_lon.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(out_of_range.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(organization.addresses.exists())

    def test_create_with_addresses(self) -> None:
        response = self.client.post(
            reverse("catalog:organization-list"),
            {"name": "ООО «Цифра»", "organization_type": "company", "legal_address": {"city": "Казань"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["organization_type"], "company")
        self.assertEqual(response.data["legal_address"]["city"], "Казань")


class OrganizationMapTestCase(APITestCase):
    """Точка на карте — по фактическому адресу, без его координат — по юридическому."""

    def setUp(self) -> None:
        self.client.force_authenticate(user_with_role(SystemRole.PLATFORM_ADMIN))

    def points(self) -> dict:
        response = self.client.get(reverse("catalog:organization-map-points"))
        return {item["id"]: (item["lat"], item["lon"]) for item in response.data}

    def test_actual_coordinates_win_and_legal_is_fallback(self) -> None:
        by_actual = OrganizationFactory(lat="57.160488", lon="65.527412")
        OrganizationAddress.objects.create(organization=by_actual, kind=AddressKind.LEGAL, **MOSCOW)
        by_legal = OrganizationFactory(city="Химки")
        OrganizationAddress.objects.create(organization=by_legal, kind=AddressKind.LEGAL, **MOSCOW)
        OrganizationFactory(city="Тюмень")

        points = self.points()

        self.assertEqual(
            points,
            {
                str(by_actual.pk): ("57.160488", "65.527412"),
                str(by_legal.pk): (MOSCOW["lat"], MOSCOW["lon"]),
            },
        )


class OrganizationLocationImportTestCase(TestCase):
    """Справочник обновляет местоположение в фактическом адресе, не трогая внесённые вручную улицу и дом."""

    def test_import_rounds_coordinates_to_six_decimal_places(self) -> None:
        """Координаты из OpenAlex могут быть точнее, чем поле карты в БД."""
        catalog_import_service.load_organizations(
            iter(
                [
                    (
                        2,
                        organization_row(
                            city="Новосибирск",
                            lat="55.04150009155273",
                            lon="82.93460083007812",
                        ),
                    ),
                ],
            ),
        )

        address = OrganizationAddress.objects.get()
        self.assertEqual(address.lat, Decimal("55.041500"))
        self.assertEqual(address.lon, Decimal("82.934601"))

    def test_import_keeps_street(self) -> None:
        catalog_import_service.load_organizations(iter([(2, organization_row(city="Тюмень", lat="57.1", lon="65.5"))]))
        address = OrganizationAddress.objects.get()
        address.street = "ул. Володарского"
        address.save()

        catalog_import_service.load_organizations(iter([(2, organization_row(city="Тюмень", lat="57.2", lon="65.6"))]))

        address.refresh_from_db()
        self.assertEqual((address.kind, address.city, address.street), (AddressKind.ACTUAL, "Тюмень", "ул. Володарского"))
        self.assertEqual(address.lat, Decimal("57.2"))

    def test_row_without_location_creates_no_address(self) -> None:
        catalog_import_service.load_organizations(iter([(2, organization_row())]))

        self.assertFalse(OrganizationAddress.objects.exists())

    def test_city_falls_back_to_legal(self) -> None:
        organization = OrganizationFactory()
        OrganizationAddress.objects.create(organization=organization, kind=AddressKind.LEGAL, city="Москва")

        self.assertEqual(organization_address_service.city(organization), "Москва")


class B2CClientAddressApiTestCase(APITestCase):
    """Адрес B2C-клиента: город открыт, улица и дом — только администратору, с журналом."""

    def setUp(self) -> None:
        self.admin = user_with_role(SystemRole.PLATFORM_ADMIN)
        self.kam = user_with_role(SystemRole.KAM)
        self.client_record = B2CClientFactory()
        self.url = reverse("catalog:b2c-client-registration-address", args=(self.client_record.pk,))

    def test_open_part_is_saved_with_the_card(self) -> None:
        self.client.force_authenticate(self.kam)

        response = self.client.patch(
            reverse("catalog:b2c-client-detail", args=(self.client_record.pk,)),
            {"address": {"region": "Тюменская область", "city": "Тюмень"}},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["address"], {"country_code": "", "region": "Тюменская область", "city": "Тюмень"})

    def test_kam_cannot_read_or_change_registration_address(self) -> None:
        self.client.force_authenticate(self.kam)

        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.put(self.url, {"street": "ул. Мира"}, format="json").status_code, 403)
        self.assertFalse(B2CClientAddressAccessLog.objects.exists())

    def test_admin_changes_and_reads_with_log(self) -> None:
        self.client.force_authenticate(self.admin)

        put = self.client.put(self.url, {"street": "ул. Мира", "house": "5", "apartment": "12"}, format="json")
        get = self.client.get(self.url)

        self.assertEqual(put.status_code, status.HTTP_200_OK, put.data)
        self.assertEqual(get.data["street"], "ул. Мира")
        self.assertEqual(get.data["apartment"], "12")
        log = list(B2CClientAddressAccessLog.objects.order_by("accessed_at").values_list("action", "fields"))
        self.assertEqual(
            log,
            [
                (PersonalDataAccessAction.UPDATE, ["street", "house", "apartment"]),
                (PersonalDataAccessAction.READ, ["street", "house", "apartment", "postal_code"]),
            ],
        )

    def test_personal_parts_are_encrypted_in_db(self) -> None:
        B2CClientAddress.objects.create(b2c_client=self.client_record, city="Тюмень", street="ул. Мира")

        with connection.cursor() as cursor:
            cursor.execute("SELECT city, street FROM catalog_b2cclientaddress")
            city, street = cursor.fetchone()

        self.assertEqual(city, "Тюмень")
        self.assertNotIn("Мира", street)

    def test_list_shows_no_personal_parts(self) -> None:
        B2CClientAddress.objects.create(b2c_client=self.client_record, city="Тюмень", street="ул. Мира")
        self.client.force_authenticate(self.admin)

        response = self.client.get(reverse("catalog:b2c-client-list"))

        self.assertEqual(response.data["results"][0]["address"], {"country_code": "", "region": "", "city": "Тюмень"})
