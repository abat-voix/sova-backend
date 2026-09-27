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
