from django.db import models
from django.db.models import Q

from sova.catalog.enum import AddressKind
from sova.catalog.models.address import AbstractAddress


class OrganizationAddress(AbstractAddress):
    """
    Адрес организации — публичный: юридический или фактический, не больше одного каждого типа.

    Координаты нужны для карты. Фактического адреса нет, если он совпадает с юридическим
    (`Organization.actual_same_as_legal`) — тогда он берётся из юридического, см. `OrganizationAddressService`.
    """

    organization = models.ForeignKey(
        to="catalog.Organization",
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name="Организация",
    )
    kind = models.CharField(
        max_length=10,
        choices=AddressKind.choices,
        verbose_name="Тип адреса",
    )
    street = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Улица",
    )
    house = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Дом, корпус, строение",
    )
    office = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Офис / помещение",
    )
    postal_code = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="Индекс",
    )
    lat = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Широта",
    )
    lon = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Долгота",
    )

    class Meta:
        verbose_name = "Адрес организации"
        verbose_name_plural = "Адреса организаций"
        ordering = ["organization", "kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind"],
                name="unique_organization_address_kind",
                violation_error_message="У организации уже есть адрес этого типа.",
            ),
            models.CheckConstraint(
                condition=Q(lat__isnull=True, lon__isnull=True) | Q(lat__isnull=False, lon__isnull=False),
                name="organization_address_coordinates_pair",
                violation_error_message="Широта и долгота указываются вместе.",
            ),
            models.CheckConstraint(
                condition=Q(lat__isnull=True) | Q(lat__gte=-90, lat__lte=90),
                name="organization_address_lat_range",
                violation_error_message="Широта — от −90 до 90.",
            ),
            models.CheckConstraint(
                condition=Q(lon__isnull=True) | Q(lon__gte=-180, lon__lte=180),
                name="organization_address_lon_range",
                violation_error_message="Долгота — от −180 до 180.",
            ),
        ]

    def __str__(self):
        return f"{self.organization} — {self.get_kind_display().lower()} адрес"

    @property
    def has_coordinates(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def full_text(self) -> str:
        """Адрес одной строкой — для договора и карточки."""
        parts = (self.postal_code, self.region, self.city, self.street, self.house, self.office)
        return ", ".join(part for part in parts if part)
