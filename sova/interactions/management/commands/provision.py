from django.core.management.base import BaseCommand, CommandError

from sova.interactions.demo import DEFAULT_COUNT, SeedError, seed_interactions


class Command(BaseCommand):
    """Наполняет базу данными для разработки — тем, чего нет в справочниках."""

    help = (
        "Создаёт тестовые взаимодействия с вузами и B2C-клиентами из справочников "
        "и назначает им действующего ответственного. Справочники загружает `loaddata --reference-data`."
    )

    def add_arguments(self, parser) -> None:
        """Ключи команды."""
        parser.add_argument(
            "--interactions",
            type=int,
            default=DEFAULT_COUNT,
            metavar="N",
            help=(
                f"Сколько тестовых взаимодействий должно быть в базе (по умолчанию {DEFAULT_COUNT}). "
                "Повторный запуск доводит их число до N, а не плодит новые."
            ),
        )

    def handle(self, *args, **options) -> None:
        """Создаёт недостающие тестовые взаимодействия и печатает сводку."""
        count = options["interactions"]
        if count <= 0:
            raise CommandError("--interactions ожидает положительное число взаимодействий.")

        try:
            result = seed_interactions(count=count)
        except SeedError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"Тестовые взаимодействия: создано {result.created} "
                f"(с вузами {result.with_universities}, с B2C-клиентами {result.with_b2c_clients}), "
                f"уже было {result.existing}. Ответственный: {result.manager}.",
            )
        )
