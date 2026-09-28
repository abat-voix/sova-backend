import datetime

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import FieldError
from django.test import SimpleTestCase, override_settings

from sova.core.crypto import blind_index, decrypt, encrypt, rotate
from sova.core.fields import EncryptedDateField, EncryptedJSONField, EncryptedTextField
from sova.core.masks import mask_email, mask_phone, mask_snils, mask_text

OLD_KEY = Fernet.generate_key().decode()
NEW_KEY = Fernet.generate_key().decode()


class CryptoTestCase(SimpleTestCase):
    """Шифрование персональных данных и HMAC-индекс для поиска."""

    def test_encrypt_hides_plaintext_and_decrypts_back(self) -> None:
        token = encrypt("cherepanona.s@test.ru")

        self.assertNotIn("cherepanona", token)
        self.assertEqual(decrypt(token), "cherepanona.s@test.ru")

    def test_same_value_encrypts_differently(self) -> None:
        """Шифр со случайным IV: по шифротексту нельзя найти совпадения."""
        self.assertNotEqual(encrypt("123"), encrypt("123"))

    def test_empty_value_stays_empty(self) -> None:
        self.assertEqual(encrypt(""), "")
        self.assertEqual(decrypt(""), "")

    def test_blind_index_is_deterministic_and_not_plaintext(self) -> None:
        index = blind_index("79990234365")

        self.assertEqual(index, blind_index("79990234365"))
        self.assertNotEqual(index, blind_index("79990234366"))
        self.assertNotIn("7999", index)
        self.assertEqual(blind_index(""), "")

    def test_rotation_reads_old_key_and_reencrypts_with_new(self) -> None:
        with override_settings(PD_ENCRYPTION_KEYS=[OLD_KEY]):
            token = encrypt("секрет")
        with override_settings(PD_ENCRYPTION_KEYS=[NEW_KEY, OLD_KEY]):
            self.assertEqual(decrypt(token), "секрет")
            rotated = rotate(token)
        with override_settings(PD_ENCRYPTION_KEYS=[NEW_KEY]):
            self.assertEqual(decrypt(rotated), "секрет")
            with self.assertRaises(InvalidToken):
                decrypt(token)


class EncryptedFieldsTestCase(SimpleTestCase):
    """Поля модели шифруют значение при записи и расшифровывают при чтении."""

    def test_text_field_round_trip(self) -> None:
        field = EncryptedTextField()
        stored = field.get_prep_value("1234 567890")

        self.assertNotIn("567890", stored)
        self.assertEqual(field.from_db_value(stored, None, None), "1234 567890")

    def test_date_field_round_trip(self) -> None:
        field = EncryptedDateField()
        stored = field.get_prep_value(datetime.date(2000, 5, 17))

        self.assertNotIn("2000", stored)
        self.assertEqual(field.from_db_value(stored, None, None), datetime.date(2000, 5, 17))
        self.assertIsNone(field.from_db_value("", None, None))
        self.assertEqual(field.to_python("2000-05-17"), datetime.date(2000, 5, 17))

    def test_json_field_round_trip(self) -> None:
        field = EncryptedJSONField()
        stored = field.get_prep_value({"Email": "a@b.ru"})

        self.assertNotIn("a@b.ru", stored)
        self.assertEqual(field.from_db_value(stored, None, None), {"Email": "a@b.ru"})
        self.assertIsNone(field.from_db_value(None, None, None))

    def test_lookups_except_isnull_are_forbidden(self) -> None:
        field = EncryptedTextField()

        self.assertIsNotNone(field.get_lookup("isnull"))
        with self.assertRaises(FieldError):
            field.get_lookup("exact")
        with self.assertRaises(FieldError):
            field.get_lookup("icontains")


class MasksTestCase(SimpleTestCase):
    """Маски персональных данных для обычных ответов API."""

    def test_masks(self) -> None:
        self.assertEqual(mask_email("cherepanona.s@test.ru"), "c***@test.ru")
        self.assertEqual(mask_phone("79990234365"), "+7 *** ***-**-65")
        self.assertEqual(mask_snils("123-456-789 45"), "***-***-*** 45")
        self.assertEqual(mask_text("4510"), "****")
        self.assertEqual(mask_email(""), "")
        self.assertEqual(mask_phone(""), "")
