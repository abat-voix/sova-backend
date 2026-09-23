"""
Конфигурация файловых хранилищ (`STORAGES`) для `sova/settings.py`.

Модуль не импортирует модели и Django app registry, поэтому его можно безопасно
импортировать из `settings.py` до инициализации приложений.
"""

import os


def s3_storage(bucket: str, location: str = "") -> dict:
    """
    Описание S3-хранилища для `STORAGES` из переменных окружения `S3_*`.

    Один и тот же провайдер (Garage по умолчанию или внешний S3) настраивается только
    переменными окружения — код не знает, с кем работает. `location` — префикс ключей
    внутри бакета (например, `"reports"`), чтобы несколько логических хранилищ могли
    делить один бакет.
    """
    return {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": bucket,
            "location": location,
            "endpoint_url": os.getenv("S3_ENDPOINT_URL") or None,
            "region_name": os.getenv("S3_REGION") or None,
            "access_key": os.getenv("S3_ACCESS_KEY_ID") or None,
            "secret_key": os.getenv("S3_SECRET_ACCESS_KEY") or None,
            "addressing_style": os.getenv("S3_ADDRESSING_STYLE", "path"),
            "signature_version": "s3v4",
            # ACL нет смысла задавать: у Garage их не существует, у внешнего S3 бакет и так
            # приватный по умолчанию. Права выдаются на уровне ключа доступа (см. план).
            "default_acl": None,
            "file_overwrite": False,
            "querystring_auth": True,
            "querystring_expire": int(os.getenv("S3_PRESIGNED_TTL", "300")),
        },
    }
