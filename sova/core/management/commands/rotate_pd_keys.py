from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from sova.core.fields import EncryptedTextField


class Command(BaseCommand):
    """
    Перешифровывает все зашифрованные поля текущим ключом (первым в `PD_ENCRYPTION_KEYS`).

    Порядок ротации: добавить новый ключ первым, оставив старый следующим, → выкатить → выполнить команду →
    убрать старый ключ.
    """

    help = "Перешифровать персональные данные текущим ключом PD_ENCRYPTION_KEYS."

    def handle(self, *args, **options) -> None:
        for model in apps.get_models():
            fields = [field.name for field in model._meta.concrete_fields if isinstance(field, EncryptedTextField)]
            if not fields:
                continue
            count = 0
            with transaction.atomic():
                # Чтение расшифровывает любым ключом, сохранение шифрует текущим
                for instance in model._default_manager.select_for_update().iterator():
                    instance.save(update_fields=fields)
                    count += 1
            self.stdout.write(f"{model._meta.label}: {count}")
