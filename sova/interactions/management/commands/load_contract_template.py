from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from sova.interactions.models import DocumentTemplate


class Command(BaseCommand):
    help = "Добавляет базовый DOCX-шаблон договора для демонстрации СОВА. Повторный запуск сохраняет существующий файл."

    def handle(self, *args, **options):
        template, _ = DocumentTemplate.objects.get_or_create(
            kind="contract", name="Базовый договор СОВА для демонстрации",
            defaults={"description": (
                "Поля contract.create: контрагент, подписант, состав, лицензии, сумма и комментарий. "
                "Реквизиты исполнителя, сроки и условия оплаты заполняются вручную. "
                "Перед подписанием требуется адаптация условий договора."
            )},
        )
        if not template.file:
            with (Path(settings.BASE_DIR) / "reference_data" / "contract_base.docx").open("rb") as source:
                template.file.save("contract_base.docx", File(source), save=False)
        template.is_active = True
        template.save()
        self.stdout.write(self.style.SUCCESS(f"Активный шаблон договора: {template.name} ({template.pk})."))
