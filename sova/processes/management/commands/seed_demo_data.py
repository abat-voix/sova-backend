from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from sova.processes.demo.scenarios import ScenarioError
from sova.processes.demo.seed import (
    DemoDataInUse,
    demo_data_exists,
    describe,
    http_variables,
    make_transport,
    purge_demo_data,
    seed_demo_data,
)

_SAFE_ENVIRONMENTS = {"development", "test", "testing"}


class Command(BaseCommand):
    """Создаёт данные для ручной проверки движка workflow по инструкции из docs/manual-testing/."""

    help = (
        "Создаёт демо-данные для ручной проверки движка workflow: справочники (вендор, направление, программа, "
        "продукты, вуз), демо-workflow и взаимодействия для сценариев. Процессы не запускает — это шаги выполнения "
        "инструкции. Печатает id для подстановки в запросы."
    )

    def add_arguments(self, parser) -> None:
        """Ключи команды."""
        parser.add_argument(
            "--username",
            help="Логин пользователя, от имени которого создаются данные (по умолчанию — первый суперпользователь).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Удалить существующие демо-данные (вместе с процессами и файлами) и создать заново.",
        )
        parser.add_argument(
            "--http",
            action="store_true",
            help="Дополнительно напечатать значения в виде `@имя = значение` для файла sova-workflow.http.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Разрешить запуск вне разработки (ENVIRONMENT не development).",
        )

    def handle(self, *args, **options) -> None:
        """Создаёт демо-данные и печатает сводку."""
        if settings.ENVIRONMENT not in _SAFE_ENVIRONMENTS and not options["force"]:
            raise CommandError(
                f"Команда создаёт демо-данные и предназначена для разработки, а ENVIRONMENT={settings.ENVIRONMENT}. "
                "Если это осознанно, добавьте --force.",
            )
        author = self._author(username=options["username"])
        if demo_data_exists() and not options["reset"]:
            raise CommandError(
                "Демо-данные уже созданы. Чтобы удалить их (вместе с процессами и файлами) и создать заново, "
                "запустите с --reset.",
            )
        if options["reset"]:
            try:
                removed = purge_demo_data()
            except DemoDataInUse as error:
                raise CommandError(f"Демо-данные нельзя удалить, на них ссылаются чужие записи: {error}") from error
            self.stdout.write(f"Удалено записей: {removed}")
        try:
            progress = seed_demo_data(transport=make_transport(user=author))
        except ScenarioError as error:
            raise CommandError(f"Не удалось создать демо-данные (изменения отменены): {error}") from error
        self.stdout.write(self.style.SUCCESS(f"Демо-данные созданы от имени {author.get_username()}."))
        for line in describe(progress):
            self.stdout.write(line)
        if options["http"]:
            self.stdout.write("")
            self.stdout.write("Переменные для sova-workflow.http (вставьте в начало файла):")
            for line in http_variables(progress):
                self.stdout.write(line)

    def _author(self, username: str | None):
        """Пользователь-автор: указанный или первый действующий суперпользователь."""
        users = get_user_model().objects
        if username:
            author = users.filter(username=username).first()
            if author is None:
                raise CommandError(f"Пользователь «{username}» не найден.")
            return author
        author = users.filter(is_superuser=True, is_active=True).order_by("pk").first()
        if author is None:
            raise CommandError("Нет суперпользователя. Создайте его: manage.py createsuperuser.")
        return author
