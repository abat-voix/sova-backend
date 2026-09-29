from django.test import SimpleTestCase

from sova.core.text import (
    email_key,
    normalize_quotes,
    normalize_telegram,
    phone_key,
    snils_key,
    quote_insensitive_key,
    split_quoted_list,
    strip_outer_quotes,
)


class NormalizeQuotesTestCase(SimpleTestCase):
    """Парные кавычки любого вида приводятся к «ёлочкам» с сохранением вложенности."""

    def test_straight_quotes_become_guillemets(self) -> None:
        self.assertEqual(normalize_quotes('ООО "Базис"'), "ООО «Базис»")

    def test_nested_straight_quotes(self) -> None:
        self.assertEqual(normalize_quotes('"Система "Яга""'), "«Система «Яга»»")

    def test_curly_and_german_quotes(self) -> None:
        self.assertEqual(normalize_quotes("“Базис” и „Яга“"), "«Базис» и «Яга»")

    def test_guillemets_and_text_without_quotes_unchanged(self) -> None:
        self.assertEqual(normalize_quotes("ОС «Аврора»"), "ОС «Аврора»")
        self.assertEqual(normalize_quotes("Python"), "Python")

    def test_apostrophe_is_not_a_quote(self) -> None:
        self.assertEqual(normalize_quotes("O'Reilly"), "O'Reilly")

    def test_unbalanced_quotes_raise(self) -> None:
        for value in ("«Базис", "Базис»", '"Базис', "«Система «Яга»"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_quotes(value)


class StripOuterQuotesTestCase(SimpleTestCase):
    """Снимается одна внешняя пара, только если она охватывает всю строку."""

    def test_strips_single_outer_pair(self) -> None:
        self.assertEqual(strip_outer_quotes("«Базис Dynamix»"), "Базис Dynamix")

    def test_keeps_inner_quotes(self) -> None:
        self.assertEqual(strip_outer_quotes("«Система «Яга»»"), "Система «Яга»")

    def test_normalizes_before_stripping(self) -> None:
        self.assertEqual(strip_outer_quotes('"Базис Dynamix"'), "Базис Dynamix")

    def test_keeps_quotes_not_covering_whole_value(self) -> None:
        self.assertEqual(strip_outer_quotes("ОС «Аврора»"), "ОС «Аврора»")
        self.assertEqual(strip_outer_quotes("«A» и «B»"), "«A» и «B»")


class SplitQuotedListTestCase(SimpleTestCase):
    """Разделители внутри кавычек не делят значение."""

    def test_splits_by_comma_and_semicolon(self) -> None:
        self.assertEqual(
            split_quoted_list("«RT.DataLake», «RT.Warehouse»; Python"),
            ["«RT.DataLake»", "«RT.Warehouse»", "Python"],
        )

    def test_separator_inside_quotes_is_kept(self) -> None:
        self.assertEqual(split_quoted_list("«Яга, Pro», «Система «А, Б»»"), ["«Яга, Pro»", "«Система «А, Б»»"])

    def test_drops_empty_items_and_normalizes(self) -> None:
        self.assertEqual(split_quoted_list(' "Базис" ,, ;  Яга  '), ["«Базис»", "Яга"])

    def test_empty_value(self) -> None:
        self.assertEqual(split_quoted_list(""), [])

    def test_custom_separators(self) -> None:
        self.assertEqual(split_quoted_list("a, b; c", separators=";"), ["a, b", "c"])

    def test_unbalanced_quotes_raise(self) -> None:
        with self.assertRaises(ValueError):
            split_quoted_list("«Базис, Яга")


class QuoteInsensitiveKeyTestCase(SimpleTestCase):
    """Ключ сравнения не зависит от вида кавычек, их наличия и регистра."""

    def test_same_key_for_any_quotes(self) -> None:
        keys = {
            quote_insensitive_key(value)
            for value in ("ООО «Базис»", 'ООО "Базис"', "ООО Базис", "ооо  „базис“")
        }
        self.assertEqual(keys, {"ооо базис"})

    def test_does_not_raise_on_unbalanced_quotes(self) -> None:
        self.assertEqual(quote_insensitive_key("«Базис"), "базис")


class PhoneKeyTestCase(SimpleTestCase):
    """Телефон сравнивается по цифрам, российские 8… и 10-значные номера приводятся к 7…."""

    def test_formats_give_same_key(self) -> None:
        keys = {phone_key(value) for value in ("+7 (900) 111-22-33", "8 900 111 22 33", "9001112233")}
        self.assertEqual(keys, {"79001112233"})

    def test_empty(self) -> None:
        self.assertEqual(phone_key(""), "")
        self.assertEqual(phone_key(" - "), "")

    def test_other_numbers_keep_digits(self) -> None:
        self.assertEqual(phone_key("+375 29 123-45-67"), "375291234567")


class EmailKeyTestCase(SimpleTestCase):
    """Email сравнивается без пробелов по краям и без учёта регистра."""

    def test_key(self) -> None:
        self.assertEqual(email_key(" Cherepanona.S@Test.ru "), "cherepanona.s@test.ru")
        self.assertEqual(email_key(""), "")


class SnilsKeyTestCase(SimpleTestCase):
    """СНИЛС сравнивается по цифрам."""

    def test_key(self) -> None:
        self.assertEqual(snils_key("123-456-789 45"), "12345678945")
        self.assertEqual(snils_key(""), "")


class NormalizeTelegramTestCase(SimpleTestCase):
    """Telegram хранится ником без @ и ссылки, регистр сохраняется."""

    def test_strips_prefixes(self) -> None:
        for value in ("@Ivanov_II", "t.me/Ivanov_II", "https://t.me/Ivanov_II", " telegram.me/Ivanov_II/ "):
            with self.subTest(value=value):
                self.assertEqual(normalize_telegram(value), "Ivanov_II")

    def test_empty(self) -> None:
        self.assertEqual(normalize_telegram(""), "")
        self.assertEqual(normalize_telegram("@"), "")

    def test_invalid_username_raises(self) -> None:
        for value in ("abc", "иванов", "ivan ov", "a" * 33):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_telegram(value)
