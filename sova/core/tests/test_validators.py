from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from sova.core.validators import validate_inn, validate_phone


class ValidateInnTestCase(SimpleTestCase):
    def test_accepts_ten_and_twelve_digits(self) -> None:
        validate_inn("7707083893")
        validate_inn("500100732259")

    def test_accepts_empty(self) -> None:
        validate_inn("")
        validate_inn(None)

    def test_rejects_letters_and_wrong_length(self) -> None:
        for value in ("77070838ab", "12345678901", "123456789", "7707 083893", "1234567890123"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_inn(value)


class ValidatePhoneTestCase(SimpleTestCase):
    def test_accepts_formatted_numbers(self) -> None:
        for value in ("+7 (495) 123-45-67", "84951234567", "9991234567", "+44 20 7946 0958"):
            with self.subTest(value=value):
                validate_phone(value)

    def test_accepts_empty(self) -> None:
        validate_phone("")

    def test_rejects_letters(self) -> None:
        for value in ("+7 999 abc-45-67", "телефон", "8 (999) 123-45-67 доб. 12"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_phone(value)

    def test_rejects_wrong_digit_count(self) -> None:
        for value in ("123-45-67", "+1234567890123456"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_phone(value)

    def test_plus_only_at_start(self) -> None:
        with self.assertRaises(ValidationError):
            validate_phone("7+9991234567")
