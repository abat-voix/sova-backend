import re
import unicodedata

# Невидимые символы, из-за которых одинаковые на вид строки не совпадают: пробелы нулевой ширины,
# BOM и мягкий перенос удаляются, неразрывные пробелы становятся обычными.
_INVISIBLE_CHARS = {
    **dict.fromkeys(map(ord, "​‌‍⁠﻿­")),
    **dict.fromkeys(map(ord, "   "), " "),
}


def normalize_text(value: str) -> str:
    """
    Приводит текст к единому виду, чтобы одинаковые на вид строки совпадали.

    Юникод — к форме NFC («й» из «и» + кратки становится одним символом), невидимые символы
    удаляются, неразрывные пробелы и повторы пробелов схлопываются в один, переносы строк
    сохраняются. Регистр не меняется — сравнение без учёта регистра делается отдельно.
    """
    text = unicodedata.normalize("NFC", value).translate(_INVISIBLE_CHARS)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def text_key(value: str) -> str:
    """Ключ сравнения строк без учёта регистра и невидимых различий (см. `normalize_text`)."""
    return normalize_text(value).casefold()


# Кавычки: «ёлочки» и „ всегда открывают, » и ” всегда закрывают; “ закрывает „ (немецкая пара), иначе открывает.
# Прямая " открывает в начале строки, после пробела или другой открывающей кавычки, иначе закрывает.
# Одинарные ' ‘ ’ кавычками не считаются — это апострофы в названиях (O'Reilly).
_OPENING_QUOTES = "«„"
_CLOSING_QUOTES = "»”"
_ALL_QUOTES = "«»„“”\"‚‘’'"
_TELEGRAM_PREFIX = re.compile(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/", flags=re.IGNORECASE)
_TELEGRAM_USERNAME = re.compile(r"[A-Za-z0-9_]{5,32}")


def _quote_marks(value: str) -> list[tuple[int, bool]]:
    """
    Позиции кавычек и их роль (True — открывающая), с проверкой парности.

    Непарные кавычки — ValueError: такое значение нельзя однозначно разобрать.
    """
    marks: list[tuple[int, bool]] = []
    stack: list[str] = []
    for index, char in enumerate(value):
        if char in _OPENING_QUOTES:
            is_opening = True
        elif char in _CLOSING_QUOTES:
            is_opening = False
        elif char == "“":
            is_opening = not (stack and stack[-1] == "„")
        elif char == '"':
            previous = value[index - 1] if index else ""
            is_opening = not previous or previous.isspace() or any(
                position == index - 1 and opening for position, opening in marks[-1:]
            )
        else:
            continue

        if is_opening:
            stack.append(char)
        elif not stack:
            raise ValueError(f"непарные кавычки в {value}")
        else:
            stack.pop()
        marks.append((index, is_opening))

    if stack:
        raise ValueError(f"непарные кавычки в {value}")
    return marks


def normalize_quotes(value: str) -> str:
    """
    Приводит парные кавычки любого вида к «ёлочкам», сохраняя вложенность: ООО "Базис" → ООО «Базис».

    Текст предварительно нормализуется (`normalize_text`). Непарные кавычки — ValueError.
    """
    text = normalize_text(value)
    chars = list(text)
    for index, is_opening in _quote_marks(text):
        chars[index] = "«" if is_opening else "»"
    return "".join(chars)


def strip_outer_quotes(value: str) -> str:
    """
    Снимает одну внешнюю пару кавычек, если она охватывает всё значение: «Система «Яга»» → Система «Яга».

    «A» и «B» и ОС «Аврора» не меняются (кроме приведения кавычек к «ёлочкам»).
    """
    text = normalize_quotes(value)
    if not (text.startswith("«") and text.endswith("»")):
        return text

    depth = 0
    for index, char in enumerate(text):
        depth += {"«": 1, "»": -1}.get(char, 0)
        if depth == 0:
            # Первая кавычка закрылась раньше конца строки — внешней пары нет.
            return normalize_text(text[1:-1]) if index == len(text) - 1 else text
    return text


def split_quoted_list(value: str, separators: str = ",;") -> list[str]:
    """
    Делит значение ячейки по разделителям, которые стоят вне кавычек; кавычки приводятся к «ёлочкам».

    «RT.DataLake», «RT.Warehouse» → два значения, «Яга, Pro» → одно. Пустые элементы отбрасываются.
    """
    text = normalize_quotes(value)
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        depth += {"«": 1, "»": -1}.get(char, 0)
        if depth == 0 and char in separators:
            items.append("".join(current))
            current = []
        else:
            current.append(char)
    items.append("".join(current))
    return [item for item in map(normalize_text, items) if item]


def quote_insensitive_key(value: str) -> str:
    """Ключ сравнения без учёта регистра и кавычек: ООО «Базис», ООО "Базис" и ООО Базис совпадают."""
    return text_key(re.sub(f"[{_ALL_QUOTES}]", " ", value))


def phone_key(value: str) -> str:
    """
    Ключ сравнения телефона: только цифры, российские 8XXXXXXXXXX и 10-значные номера — с кодом 7.

    Телефон — дополнительный признак при сопоставлении людей, а не идентификатор: номер может смениться.
    """
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("8"):
        return f"7{digits[1:]}"
    if len(digits) == 10:
        return f"7{digits}"
    return digits


def normalize_telegram(value: str) -> str:
    """
    Ник Telegram без @ и ссылки: @ivanov, t.me/ivanov, https://t.me/ivanov → ivanov; регистр сохраняется.

    Пустое значение — пустая строка; недопустимый ник (не 5–32 символа A-Z, 0-9, _) — ValueError.
    """
    username = _TELEGRAM_PREFIX.sub("", normalize_text(value)).strip("/").removeprefix("@")
    if username and not _TELEGRAM_USERNAME.fullmatch(username):
        raise ValueError(f"недопустимый ник Telegram: {value}")
    return username
