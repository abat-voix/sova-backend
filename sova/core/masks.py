"""Маски персональных данных для обычных ответов API: полное значение видно только по отдельному праву."""

import re


def mask_text(value: str) -> str:
    """Скрывает значение целиком, сохраняя длину."""
    return "*" * len(value or "")


def mask_email(value: str) -> str:
    """cherepanona.s@test.ru → c***@test.ru."""
    if not value:
        return ""
    local, _, domain = value.partition("@")
    return f"{local[:1]}***@{domain}" if domain else mask_text(value)


def mask_phone(value: str) -> str:
    """79990234365 → +7 *** ***-**-65."""
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    return f"+7 *** ***-**-{digits[-2:]}"


def mask_snils(value: str) -> str:
    """123-456-789 45 → ***-***-*** 45: видна только контрольная сумма."""
    digits = re.sub(r"\D", "", value or "")
    if not digits:
        return ""
    return f"***-***-*** {digits[-2:]}"
