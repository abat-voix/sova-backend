import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sova.catalog.models import Direction, Program, Organization
from sova.core.crypto import blind_index
from sova.core.text import email_key
from sova.integrations.api.serializers import IntegrationMappingSerializer
from sova.integrations.models import IntegrationMapping
from sova.interactions.models import Interaction, InteractionProgram
from sova.training.enum import TrainingStreamStatus
from sova.training.models import Learner, TrainingApplicationLearner, TrainingStream
from sova.training.services.application import training_application_service

MAPPING_NAME = "Сайт: оплаты обучения"
MAPPING_RULES = [
    ("$.Номер потока", "stream", True),
    ("$.Курс", "course", True),
    ("$.Фамилия", "last_name", True),
    ("$.Имя", "first_name", True),
    ("$.Отчество", "middle_name", False),
    ("$.Email", "email", False),
    ("$.Телефон", "phone", False),
]


class Command(BaseCommand):
    help = (
        "Демо-данные для проверки загрузки «Данные оплат.json»: потоки по курсам, обучающиеся в заявках потоков "
        "(режим загрузки «для потока») и входящий маппинг интеграции «Оплата обучения». Пишет копию JSON, где "
        "«Номер потока» заменён на id созданного потока, — её загружают в маппинг. Повторный запуск идемпотентен."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=str(Path(settings.BASE_DIR) / "docs" / "Хакатон" / "Данные оплат.json"),
            help="Исходный JSON оплат",
        )
        parser.add_argument("--output", default="payments_demo.json", help="Куда записать JSON с id потоков")
        parser.add_argument("--reset-paid", action="store_true", help="Снять отметки оплаты у демо-участников")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            rows = json.loads(Path(options["file"]).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CommandError(f"Не удалось прочитать {options['file']}: {error}") from error
        if not isinstance(rows, list):
            raise CommandError("Ожидается JSON-массив строк оплат.")

        interaction = self._interaction()
        streams: dict[tuple[str, str], TrainingStream] = {}
        output = []
        for row in rows:
            if row is None:
                output.append(None)
                continue
            key = (str(row["Номер потока"]), row["Курс"])
            if key not in streams:
                streams[key] = self._stream(interaction, *key)
            stream = streams[key]
            participant = self._participant(stream, row)
            if options["reset_paid"] and participant.is_paid:
                training_application_service.set_paid(participant, False)
            output.append({**row, "Номер потока": str(stream.pk)})

        mapping = self._mapping()
        Path(options["output"]).write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"Потоков: {len(streams)}, участников: {len(output) - output.count(None)}. "
            f"Маппинг «{mapping.name}» ({mapping.pk}). JSON для загрузки: {options['output']}"
        ))

    @staticmethod
    def _interaction() -> Interaction:
        organization, _ = Organization.objects.get_or_create(name="Демо-вуз: оплаты обучения")
        interaction = Interaction.objects.filter(organization=organization).first()
        return interaction or Interaction.objects.create(organization=organization)

    @staticmethod
    def _stream(interaction: Interaction, number: str, course: str) -> TrainingStream:
        direction, _ = Direction.objects.get_or_create(name="Демо: ИТ Школа")
        program, _ = Program.objects.get_or_create(name=course, defaults={"direction": direction})
        interaction_program, _ = InteractionProgram.objects.get_or_create(interaction=interaction, program=program)
        stream, _ = TrainingStream.objects.get_or_create(
            interaction_program=interaction_program,
            name=f"Демо-поток {number}",
            defaults={"status": TrainingStreamStatus.ENROLLMENT_OPEN},
        )
        return stream

    @staticmethod
    def _participant(stream: TrainingStream, row: dict) -> TrainingApplicationLearner:
        email = row.get("Email") or ""
        learner = Learner.objects.filter(email_hash=blind_index(email_key(email))).first() if email else None
        learner = learner or Learner(
            last_name=row["Фамилия"],
            first_name=row["Имя"],
            middle_name=row.get("Отчество") or "",
            email=email,
            phone=row.get("Телефон") or "",
        )
        if learner._state.adding:
            learner.save()
        participant = TrainingApplicationLearner.objects.filter(application__stream=stream, learner=learner).first()
        if participant is None:
            application = training_application_service.create_application(
                stream=stream, learners=[learner], user=None
            )
            participant = application.participants.get()
        return participant

    @staticmethod
    def _mapping() -> IntegrationMapping:
        data = {
            "name": MAPPING_NAME,
            "system": "cms",
            "eventType": "training.payment.received",
            "direction": "incoming",
            "entity": "training_payment",
            "isActive": True,
            "rules": [
                {"sourcePath": source, "targetField": target, "required": required, "defaultValue": None}
                for source, target, required in MAPPING_RULES
            ],
        }
        serializer = IntegrationMappingSerializer(IntegrationMapping.objects.filter(name=MAPPING_NAME).first(), data=data)
        serializer.is_valid(raise_exception=True)
        return serializer.save()
