"""
Шифрование персональных данных (152-ФЗ, приказ ФСТЭК № 117).

Значения шифруются Fernet (AES-128-CBC + HMAC) с ключами `settings.PD_ENCRYPTION_KEYS`: первый ключ шифрует,
остальные только расшифровывают — так ключ меняется без простоя (`manage.py rotate_pd_keys`). Шифротекст одного и
того же значения каждый раз разный, поэтому искать по нему нельзя: для поиска и сопоставления рядом хранится
`blind_index` — HMAC-SHA256 нормализованного значения с отдельным ключом `settings.PD_HASH_KEY`.

Пустая строка не шифруется: пустое поле не несёт персональных данных.
"""

import hashlib
import hmac

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


def _fernet() -> MultiFernet:
    """Набор ключей из настроек; строится на каждый вызов, чтобы подхватывать смену ключей без перезапуска."""
    return MultiFernet([Fernet(key) for key in settings.PD_ENCRYPTION_KEYS])


def encrypt(value: str) -> str:
    """Шифрует строку текущим ключом."""
    if not value:
        return ""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Расшифровывает строку любым из ключей; чужой или повреждённый шифр — `cryptography.fernet.InvalidToken`."""
    if not token:
        return ""
    return _fernet().decrypt(token.encode()).decode()


def rotate(token: str) -> str:
    """Перешифровывает шифр текущим ключом."""
    if not token:
        return ""
    return _fernet().rotate(token.encode()).decode()


def blind_index(value: str) -> str:
    """HMAC-индекс уже нормализованного значения — для точного поиска по зашифрованному полю."""
    if not value:
        return ""
    return hmac.new(settings.PD_HASH_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
